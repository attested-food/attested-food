#!/usr/bin/env bash
# Upload out/raw/<id>.pdf to s3://<bucket>/<key> as given in data/<id>.json. Creates the bucket
# (us-east-1) with public read on reports/* only (no ListBucket) if it does not exist yet.
# usage: scripts/upload.sh [<id> ...]   (default: every data/*.json). AWS_PROFILE is honoured.
set -euo pipefail
cd "$(dirname "$0")/.."

ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  for f in data/*.json; do ids+=("$(basename "$f" .json)"); done
fi

bucket=$(node -p "require('./data/${ids[0]}.json').s3.bucket")
if ! aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
  aws s3api create-bucket --bucket "$bucket" --region us-east-1 >/dev/null
  aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false
  aws s3api put-bucket-policy --bucket "$bucket" --policy "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{\"Sid\": \"PublicReadReports\", \"Effect\": \"Allow\", \"Principal\": \"*\",
      \"Action\": \"s3:GetObject\", \"Resource\": \"arn:aws:s3:::$bucket/reports/*\"}]
  }"
  echo "created s3://$bucket (public read on reports/*)"
fi

for id in "${ids[@]}"; do
  key=$(node -p "require('./data/$id.json').s3.key")
  aws s3api put-object --bucket "$bucket" --key "$key" --body "out/raw/$id.pdf" \
    --content-type application/pdf >/dev/null
  echo "https://$bucket.s3.amazonaws.com/$key"
done
