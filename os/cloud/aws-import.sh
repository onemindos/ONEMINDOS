#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Turn onemind-cloud-aws-<v>.raw (or .raw.xz) into an EC2 AMI (docs/leap/core/CLOUD-IMAGES.md §3.1):
# upload to S3, import-snapshot (format RAW), register-image with UEFI boot mode, ENA and IMDSv2.
# import-snapshot, not import-image: import-image inspects and rewrites the OS and supports only listed
# distributions; a snapshot is imported byte for byte.
# Needs: the AWS CLI v2 logged in to YOUR account, an S3 bucket, and the "vmimport" service role
# (AWS VM Import/Export user guide, "Required service role"). Nothing here runs in CI.
#   aws-import.sh <image.raw|image.raw.xz> <s3-bucket> [region]
set -eu
. "$(dirname "$0")/lib.sh"
need aws xz sha256sum
[ $# -ge 2 ] || { sed -n 's/^#   //p' "$0"; exit 2; }
RAW=$(unxz_keep "$1"); BUCKET=$2; REGION=${3:-$(aws configure get region)}
verify "$RAW"
N=$(basename "$RAW" .raw); V=${N#onemind-cloud-aws-}
KEY=onemind/$N.raw
echo "== upload s3://$BUCKET/$KEY"
aws s3 cp --region "$REGION" "$RAW" "s3://$BUCKET/$KEY"
echo "== import-snapshot"
TASK=$(aws ec2 import-snapshot --region "$REGION" --description "OneMind $V (cloud-aws)" \
  --disk-container "Format=RAW,UserBucket={S3Bucket=$BUCKET,S3Key=$KEY}" --query ImportTaskId --output text)
while :; do
  set -- $(aws ec2 describe-import-snapshot-tasks --region "$REGION" --import-task-ids "$TASK" \
    --query 'ImportSnapshotTasks[0].SnapshotTaskDetail.[Status,SnapshotId,Progress]' --output text)
  echo "   $TASK: $*"
  case "$1" in completed) SNAP=$2; break ;; deleted|deleting|error) echo "import failed" >&2; exit 1 ;; esac
  sleep 30
done
echo "== register-image from $SNAP"
AMI=$(aws ec2 register-image --region "$REGION" --name "onemind-$(slug "$V")" \
  --description "OneMind OS $V (cloud-aws, UEFI)" --architecture x86_64 --virtualization-type hvm \
  --boot-mode uefi --ena-support --imds-support v2.0 --root-device-name /dev/xvda \
  --block-device-mappings "DeviceName=/dev/xvda,Ebs={SnapshotId=$SNAP,VolumeType=gp3,DeleteOnTermination=true}" \
  --query ImageId --output text)
echo "AMI $AMI in $REGION. The uploaded object can be deleted: aws s3 rm s3://$BUCKET/$KEY"
cat <<HINT
Launch a hub (UEFI needs a Nitro instance type; 4 GiB RAM or more; open only port 22 to you):
  aws ec2 run-instances --region $REGION --image-id $AMI --instance-type t3.medium --key-name <your-key-pair> \\
    --security-group-ids <sg> --user-data file://hub.yaml \\
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=40,VolumeType=gp3}'
Owner token: aws ec2 get-console-output --latest --instance-id <id> --output text | grep 'ONEMIND OWNER TOKEN'
         or: ssh admin@<ip> sudo cat /run/onemind/owner-token   (until the first reboot)
HINT
