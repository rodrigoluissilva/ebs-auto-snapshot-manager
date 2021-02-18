#!/usr/bin/env python

""" AWS Lambda Function to manage EBS Snapshot

This Lambda Function provides automatic EBS Snapshot
creation, copy and deletion as backup strategy.

Features

 - Automatic snapshot creation configured using volume tags
 - Automatic snapshot deletion on expiration date
 - Automatic cross region snapshot copy
 - Can check all or pre-defined aws region
 - Can run locally outside AWS Lambda

-------

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

__author__ = "Rodrigo Luis Silva"
__url__ = "https://github.com/rodrigoluissilva/ebs-auto-snapshot-manager"
__deprecated__ = False
__license__ = "GPLv3"
__status__ = "Production"
__version__ = "1.0.0"

import os
import uuid
import boto3
import datetime
import locale
import logging

from botocore.exceptions import ClientError

try:
    locale.setlocale(locale.LC_TIME, 'en_US.utf8')
except locale.Error:
    pass

logging.basicConfig(format='%(asctime)-15s [%(name)s] [%(levelname)s] '
                           '(%(request_id)s) %(aws_region)s %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ec2 = boto3.client('ec2')

default_tag = os.environ.get('custom_tag', 'scheduler:ebs-auto-snapshot-creation')
default_retention_days = int(os.environ.get('default_retention_days', 7))
custom_aws_regions = os.environ.get('custom_aws_regions', None)

if custom_aws_regions is not None:
    aws_regions = [region.strip().lower() for region in custom_aws_regions.split(',')]
else:
    aws_regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]


def lambda_handler(event=None, context=None):

    if context is None:
        request_id = uuid.uuid4()
    else:
        request_id = context.aws_request_id

    today_date = datetime.date.today()
    today_datetime = datetime.datetime.now().strftime('%Y-%M-%d_%H-%M-%S')
    today_weekday = datetime.date.strftime(today_date, '%a').lower()
    today_day = int(datetime.date.strftime(today_date, '%d'))

    for aws_region in aws_regions:

        log_extra = {'request_id': request_id, 'aws_region': aws_region}

        logger.debug('Entering aws region', extra=log_extra)

        ec2cli = boto3.client('ec2', region_name=aws_region)
        ec2res = boto3.resource('ec2', region_name=aws_region)

        """
        Check all volumes with relevant tag and take a snapshot if needed
        """
        volumes = ec2cli.describe_volumes(Filters=[{'Name': 'tag-key',
                                                    'Values': [default_tag]},
                                                   {'Name':   'status',
                                                    'Values': ['available',
                                                               'in-use']},
                                                   ]
                                          )['Volumes']
        for volume in volumes:
            for tag in volume['Tags']:
                if tag['Key'] == default_tag:
                    try:
                        config = {k.strip().lower(): v.strip().lower() for k, v in
                                  [option.split('=') for option in tag['Value'].split(';')]}
                    except ValueError:
                        config = {'enable': False, 'parse_error': tag['Value']}

            copy_tags = True \
                if config.get('copytags') in ('true', 'yes') \
                else False
            backup_enable = True \
                if config.get('enable') in ('true', 'yes') \
                else False
            schedule_type = config.get('type') \
                if config.get('type') in ('always', 'daily', 'weekly', 'monthly') \
                else None
            retention_days = int(config.get('retention')) \
                if config.get('retention', '').isdigit() \
                else default_retention_days
            when_to_run = config.get('when', '').split(',')
            destination_copy = config.get('copyto', '').split(',')
            expire_date = str(today_date + datetime.timedelta(days=retention_days))
            volume_id = volume['VolumeId']

            if backup_enable:

                if schedule_type == 'always':
                    description_date = str(today_datetime)
                else:
                    description_date = str(today_date)

                if (
                        (
                                schedule_type == 'weekly' and today_weekday
                                not in [when.strip().lower()[:3] for when in when_to_run]
                        )
                        or
                        (
                                schedule_type == 'monthly' and today_day
                                not in [int(d) for d in when_to_run
                                        if d.strip().isdigit() and int(d) in range(1, 32)]
                        )
                ):
                    logger.debug('Skipping volume ({}) snapshot will be '
                                 'taken ({}) on ({})'.format(volume_id,
                                                             schedule_type.title(),
                                                             ','.join(when_to_run).title()),
                                 extra=log_extra)
                    continue

                volume_info = ec2res.Volume(volume_id)

                if len(volume_info.attachments) != 0:
                    instance_id = volume_info.attachments[0]['InstanceId']
                    instance_device = volume_info.attachments[0]['Device']
                    instance = ec2res.Instance(instance_id)
                    for tag in instance.tags:
                        if tag['Key'] == 'Name':
                            instance_name = tag['Value']
                else:
                    instance_id = '-'
                    instance_name = '-'
                    instance_device = '-'

                description = 'Snapshot of [{}] attached to [{}] ' \
                              '[{}] as [{}] on [{}]'.format(volume_id,
                                                            instance_id,
                                                            instance_name,
                                                            instance_device,
                                                            description_date)

                snapshots = ec2cli.describe_snapshots(Filters=[{'Name': 'description',
                                                                'Values': [description]},
                                                               ])['Snapshots']
                if len(snapshots) == 0:
                    snap = volume_info.create_snapshot(Description=description)

                    if copy_tags:
                        snap.create_tags(Tags=volume['Tags'])

                    new_tag_value = expire_date + ';' + ','.join(destination_copy)
                    snap.create_tags(Tags=[{'Key': default_tag,
                                            'Value': new_tag_value}])

                    logger.info('Snapshot for volume ({}) created as '
                                '({}) to be removed on ({})'.format(volume_id,
                                                                    snap.snapshot_id,
                                                                    expire_date),
                                extra=log_extra)
                else:
                    logger.info('Snapshot for volume ({}) already taken'.format(volume_id),
                                extra=log_extra)
            else:
                if config.get('parse_error', False):
                    logger.warning('Parser error for volume ({}) [{}]'.format(volume_id,
                                                                              config.get('parse_error')),
                                   extra=log_extra)
                else:
                    logger.debug('Backup Disabled for volume ({})'.format(volume_id),
                                 extra=log_extra)

        """
        Remove expired snapshots and copy images to the destination region
        """
        snapshots = ec2cli.describe_snapshots(Filters=[{'Name': 'tag-key',
                                                        'Values': [default_tag]},
                                                       {'Name': 'status',
                                                        'Values': ['completed']},
                                                       ])['Snapshots']
        for snapshot in snapshots:
            parser_error = False
            for tag in snapshot['Tags']:
                if tag['Key'] == default_tag:
                    try:
                        expire_date, destination_copy = tag['Value'].split(';')
                    except ValueError:
                        parser_error = tag['Value']
            if parser_error:
                logger.warning('Parser error for snapshot ({}) [{}]'.format(snapshot['SnapshotId'],
                                                                            tag['Value']),
                               extra=log_extra)
                continue

            expire_date = datetime.datetime.strptime(expire_date, '%Y-%m-%d').date()
            destination_copy = [dest.lower().strip() for dest in destination_copy.split(',')]

            if expire_date <= today_date:
                try:
                    ec2res.Snapshot(snapshot['SnapshotId']).delete()
                    logger.info('Removing snapshot ({}) expired on ({})'.format(snapshot['SnapshotId'],
                                                                                expire_date),
                                extra=log_extra)
                except Exception as e:
                    logger.error('Error removing snapshot ({}) expired '
                                 'on ({}): {}'.format(snapshot['SnapshotId'],
                                                      expire_date,
                                                      e.response['Error']['Message']),
                                 extra=log_extra)
            else:
                logger.debug('Keeping snapshot ({}) until ({})'.format(snapshot['SnapshotId'],
                                                                       expire_date),
                             extra=log_extra)

            for destination in destination_copy:
                if destination in aws_regions:
                    try:
                        snapshot_source = boto3.resource('ec2', region_name=aws_region).Snapshot(snapshot['SnapshotId'])

                        description = snapshot_source.description \
                                      + ' [Copy of ({}) from ({})]'.format(snapshot['SnapshotId'],
                                                                           aws_region)

                        snapshot_target_id = (
                            boto3.resource('ec2', region_name=destination)
                                .Snapshot(snapshot['SnapshotId'])
                                .copy(Description=description, SourceRegion=aws_region)
                        )['SnapshotId']
                        snapshot_target = boto3.resource('ec2', region_name=destination).Snapshot(snapshot_target_id)

                        tag_value = [dest for dest in destination_copy if dest not in aws_regions]
                        new_source_tags = [{'Key': default_tag,
                                            'Value': str(expire_date) + ';' + ','.join(tag_value)},
                                           ]
                        new_target_tags = [{'Key': default_tag,
                                            'Value': str(expire_date) + ';None'},
                                           ]
                        snapshot_target.create_tags(Tags=snapshot_source.tags)
                        snapshot_target.create_tags(Tags=new_target_tags)
                        snapshot_source.create_tags(Tags=new_source_tags)

                        logger.info('Copying snapshot ({}) '
                                    'from ({}) to ({}) as ({})'.format(snapshot['SnapshotId'],
                                                                       aws_region,
                                                                       destination,
                                                                       snapshot_target_id),
                                    extra=log_extra)
                    except Exception as e:
                        if e.response['Error']['Code'] == 'ResourceLimitExceeded':
                            logger.info('Skipping snapshot ({}): '
                                        '{}'.format(snapshot['SnapshotId'],
                                                    e.response['Error']['Message']),
                                        extra=log_extra)
                        else:
                            logger.error("Error copying snapshot ({}) from ({}) "
                                         "to ({}): {}".format(snapshot['SnapshotId'],
                                                              aws_region,
                                                              destination,
                                                              e.response['Error']['Message']),
                                         extra=log_extra)
                        continue

        logger.debug('Exiting aws region'.format(), extra=log_extra)


if __name__ == '__main__':
    lambda_handler()
