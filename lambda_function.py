import json, os, boto3, botocore

TAG_KEY = os.getenv('TAG_KEY', 'CreatedBy')

ec2 = boto3.client('ec2')
s3  = boto3.client('s3')
rds = boto3.client('rds')
lam = boto3.client('lambda')
ecr = boto3.client('ecr')
logs = boto3.client('logs')
eks = boto3.client('eks')

def _actor_arn(detail: dict) -> str:
    ui = detail.get('userIdentity', {}) or {}
    arn = ui.get('arn')
    # Prefer session issuer if this was an AssumedRole (common in CI/CD)
    if ui.get('type') == 'AssumedRole':
        arn = ui.get('sessionContext', {}).get('sessionIssuer', {}).get('arn', arn)
    return arn or ui.get('principalId', 'unknown')

def tag_ec2_runinstances(detail, actor):
    items = (((detail.get('responseElements') or {}).get('instancesSet') or {}).get('items') or [])
    instance_ids = [i.get('instanceId') for i in items if i.get('instanceId')]
    if instance_ids:
        ec2.create_tags(Resources=instance_ids, Tags=[{'Key': TAG_KEY, 'Value': actor}])
        # tag volumes created at launch
        vols = []
        for i in items:
            for bd in (i.get('blockDeviceMapping') or []):
                ebs = bd.get('ebs') or {}
                if ebs.get('volumeId'):
                    vols.append(ebs['volumeId'])
        if vols:
            ec2.create_tags(Resources=vols, Tags=[{'Key': TAG_KEY, 'Value': actor}])

def tag_ec2_createvolume(detail, actor):
    vol_id = (detail.get('responseElements') or {}).get('volumeId')
    if vol_id:
        ec2.create_tags(Resources=[vol_id], Tags=[{'Key': TAG_KEY, 'Value': actor}])

def tag_s3_createbucket(detail, actor):
    bucket = (detail.get('requestParameters') or {}).get('bucketName')
    if bucket:
        s3.put_bucket_tagging(Bucket=bucket, Tagging={'TagSet': [{'Key': TAG_KEY, 'Value': actor}]})

def tag_rds_instance(detail, actor, account, region):
    arn = (detail.get('responseElements') or {}).get('dBInstanceArn')
    if not arn:
        dbid = (detail.get('requestParameters') or {}).get('dBInstanceIdentifier')
        if dbid:
            arn = f"arn:aws:rds:{region}:{account}:db:{dbid}"
    if arn:
        rds.add_tags_to_resource(ResourceName=arn, Tags=[{'Key': TAG_KEY, 'Value': actor}])

def tag_lambda_function(detail, actor):
    arn = (detail.get('responseElements') or {}).get('functionArn')
    if arn:
        lam.tag_resource(Resource=arn, Tags={TAG_KEY: actor})

def tag_ecr_repo(detail, actor):
    arn = ((detail.get('responseElements') or {}).get('repository') or {}).get('repositoryArn')
    if arn:
        ecr.tag_resource(resourceArn=arn, tags=[{'Key': TAG_KEY, 'Value': actor}])

def tag_log_group(detail, actor, account, region):
    name = (detail.get('requestParameters') or {}).get('logGroupName')
    if name:
        # CloudWatch Logs uses tag_log_group by name
        logs.tag_log_group(logGroupName=name, tags={TAG_KEY: actor})

def tag_eks_cluster(detail, actor):
    arn = ((detail.get('responseElements') or {}).get('cluster') or {}).get('arn')
    if arn:
        eks.tag_resource(resourceArn=arn, tags={TAG_KEY: actor})

def lambda_handler(event, context):
    detail = event.get('detail', {}) or {}
    account = event.get('account')
    region = detail.get('awsRegion') or event.get('region')
    actor = _actor_arn(detail)

    es = detail.get('eventSource')
    en = detail.get('eventName')

    print(f"Received {es}:{en} by {actor}")
    try:
        if es == 'ec2.amazonaws.com' and en == 'RunInstances':
            tag_ec2_runinstances(detail, actor)
        elif es == 'ec2.amazonaws.com' and en == 'CreateVolume':
            tag_ec2_createvolume(detail, actor)
        elif es == 's3.amazonaws.com' and en == 'CreateBucket':
            tag_s3_createbucket(detail, actor)
        elif es == 'rds.amazonaws.com' and en in ('CreateDBInstance','RestoreDBInstanceFromDBSnapshot'):
            tag_rds_instance(detail, actor, account, region)
        elif es == 'lambda.amazonaws.com' and en == 'CreateFunction20150331':
            tag_lambda_function(detail, actor)
        elif es == 'ecr.amazonaws.com' and en == 'CreateRepository':
            tag_ecr_repo(detail, actor)
        elif es == 'logs.amazonaws.com' and en == 'CreateLogGroup':
            tag_log_group(detail, actor, account, region)
        elif es == 'eks.amazonaws.com' and en == 'CreateCluster':
            tag_eks_cluster(detail, actor)
        else:
            print(f"No handler for {es}:{en}")
    except botocore.exceptions.ClientError as e:
        print(f"Tagging error: {e}")
        raise

    return {'status': 'ok', 'actor': actor, 'handled': f'{es}:{en}'}
