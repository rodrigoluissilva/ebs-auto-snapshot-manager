
# ebs-auto-snapshot-manager

> AWS Lambda function written in Python to manage EBS Snapshots

## Description

The Lambda function "*ebs-auto-snapshot-manager*" provides automatic EBS snapshot creation, copy and deletion as backup strategy.

## Features

 - Automatic snapshot creation configured using volume tags
 - Automatic snapshot deletion on expiration date
 - Automatic cross region snapshot copy
 - Can check all or pre-defined aws region

## Lambda Creation

Follow these steps to get your lambda function running.

### IAM Role

Add this IAM role. It will be attached to your lambda function.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

You can add via command line

```
aws iam create-role --role-name lambda-ebs-auto-snapshot-manager --path /service-role/ --description "Automatic EBS Snapshot creation and deletion" --assume-role-policy-document https://raw.githubusercontent.com/rodrigoluissilva/ebs-auto-snapshot-manager/master/lambda-role.json
```

### IAM Policy

Now you have to attach this policy to allow a few actions to be performed.

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:CreateLogGroup",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeRegions",
                "ec2:DescribeVolumes",
                "ec2:DescribeSnapshots",
                "ec2:DescribeInstances",
                "ec2:CreateSnapshot",
                "ec2:CreateTags",
                "ec2:CopySnapshot"
            ],
            "Resource": "*"
        }
    ]
}
```

This can be done via command line

```
aws iam put-role-policy --role-name lambda-ebs-auto-snapshot-manager --policy-name ebs-auto-snapshot-manager --policy-document https://raw.githubusercontent.com/rodrigoluissilva/ebs-auto-snapshot-manager/master/lambda-policy.json
```

### Lambda Function

#### Console

Add a new Lambda function using these options.

**Name**: ebs-auto-snapshot-manager
**Runtime**: Python 3.6
**Existing Role**: service-role/lambda-ebs-auto-snapshot-manager

![Lambda Create Function Sample Screen](https://image.prntscr.com/image/7QQ3S4K7TsuuaJPqhObihw.png)

Change the **timeout to 5 minutes** and add some useful description.

![Lambda Function Basic Settings Sample Screen](https://image.prntscr.com/image/wXq8S9bDT729gKk5nkBBvg.png)

Paste the code from the file *ebs-auto-snapshot-manager.py* in the Lambda Function Code area.

You can set a test event using the "**Scheduled Event**" template.

#### Command Line

Download the file *ebs-auto-snapshot-manager.py*.
Rename it to *lambda_function.py*.
Compress it as a *zip file*.

Get the IAM Role ARN using this command.

```
aws iam get-role --role-name lambda-ebs-auto-snapshot-manager
```

Replace the ARN by the one from the previous command.

```
aws lambda create-function --region us-east-1 --function-name ebs-auto-snapshot-manager --description "Provides automatic EBS snapshot rotation" --zip-file fileb://lambda_function.zip --handler lambda_function.lambda_handler --runtime python3.6 --timeout 300 --role arn:aws:iam::XXXXXXXXXXXX:role/lambda-ebs-auto-snapshot-manager
```

## Schedule

This lambda function is triggered by one CloudWatch Event Rule.
Run this command to set it to run at 3 am everyday.

```
aws events put-rule --name ebs-auto-snapshot-manager --schedule-expression "cron(0 3 * * ? *)" --description "Trigger the ebs-auto-snapshot-manager function"
```

Add permission to CloudWatch invoke the Lambda Function.
Use the ARN from the previous command.

```
aws lambda add-permission --function-name ebs-auto-snapshot-manager --statement-id ebs-auto-snapshot-manager --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn arn:aws:events:us-east-1:XXXXXXXXXXXX:rule/ebs-auto-snapshot-manager
```

Get the Lambda Function ARN with this command.

```
aws lambda get-function-configuration --function-name ebs-auto-snapshot-manager
```

Replace this ARN by the one from the previous command.

```
aws events put-targets --rule ebs-auto-snapshot-manager --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:XXXXXXXXXXXX:function:ebs-auto-snapshot-manager"
```

## Volume Configuration

The default tag is "*scheduler:ebs-auto-snapshot-creation*"

To enable the backup, add this tag and the value following the specific pattern as described bellow.

**Key**: scheduler:ebs-auto-snapshot-creation

**Value**: Enable=Yes;Type=Weekly;When=Tuesday;Retention=2;CopyTags=Yes;CopyTo=us-west-1

The minimum setting for a daily snapshot creation is

**Key**: scheduler:ebs-auto-snapshot-creation

**Value**: Enable=Yes

### Parameters details

| Parameter | Description |Values|
|--|--|--|
| **Enable** |Enable or Disable snapshot auto creation. <br> You need at least this parameter to enable the daily snapshot creation.| **Yes** – Enable<br>**No** – Disable (**default**) |
| **Type** | How often to take an snapshot. | **Always** – Will take one snapshot on each execution<br>**Daily** – One snapshot per day (**default**)<br>**Weekly** – One snapshot on the weekday defined on the parameter "When"<br>**Monthly** – One snapshot on the day defined on the parameter "When" |
|**When**|When this snapshot will be taken<br>Could be one or more values.<br><br>When=Tuesday<br>When=Sunday, Thursday<br>When=Mon, Sat<br>When=25<br>When=1, 15<br>When=1, 10, 20|**Always and Daily**<br>This option is not used<br><br>**Weekly**<br>Sun, Mon, ..., Sat<br>Sunday, Monday, ..., Saturday<br><br>**Monthly**<br>1, 2, 3, ..., 31|
|**Retention**|The number of days to keep the snapshot.|1, 2, 3, 4, 5, ...<br> (**default**: 2)|
|**CopyTags**|Copy volume tags to the snapshot.|**Yes** – Copy all volume tags<br>**No** – Don’t copy volume tags (**default**)|
|**CopyTo**|Make a copy of this snapshot to a different region.<br>Could be one or more values.<br><br>CopyTo=us-east-2<br>CopyTo=us-east-2, us-west-1|ap-south-1, eu-west-3, eu-west-2, eu-west-1, ap-northeast-2, ap-northeast-1, sa-east-1, ca-central-1, ap-southeast-1, ap-southeast-2, eu-central-1, us-east-1, us-east-2, us-west-1, us-west-2<br><br>**Default**: None|

## Lambda Environment Variables

You can set a few environment variables to control how the Lambda Function will behave.

Key|Description|Value
-|-|-
**custom_aws_regions**|A list of AWS Regions to be used during the execution time.<br>Could be one or more regions.<br><br>custom_aws_regions=us-east-1, us-east-2, us-west-1|Any valid AWS region.
**custom_tag**|Define the tag name to be used.|Any valid tag name.
**default_retention_days**|The default retention period in days.|Any valid number of days.