#!/usr/bin/env bash
# Upload raw PDFs to S3 and check the served bytes against the local file (sha256).
#   scripts/upload.sh [<id> ...]                      out/raw/<id>.pdf -> key from data/<id>.json
#   scripts/upload.sh --variant <v> [<id> ...]        out/opt/<v>/raw/<id>.pdf -> key from data/opt-keys.json
# Creates the bucket (us-east-1) with public read on reports/* only (no ListBucket) if missing.
# AWS_PROFILE is honoured.
set -euo pipefail
cd "$(dirname "$0")/.."

variant=""
if [ "${1:-}" = "--variant" ]; then variant=$2; shift 2; fi
ids=("$@")
if [ ${#ids[@]} -eq 0 ]; then
  for f in data/*.json; do [ "$f" = data/opt-keys.json ] || ids+=("$(basename "$f" .json)"); done
fi

bucket=$(node -p "require('./data/${ids[0]}.json').s3.bucket")
if ! aws s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
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

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
for id in "${ids[@]}"; do
  if [ -n "$variant" ]; then
    key=$(node -p "require('./data/opt-keys.json')['$variant']['$id']")
    file="out/opt/$variant/raw/$id.pdf"
  else
    key=$(node -p "require('./data/$id.json').s3.key")
    file="out/raw/$id.pdf"
  fi
  aws s3api put-object --bucket "$bucket" --key "$key" --body "$file" --content-type application/pdf >/dev/null
  curl -sf -o "$tmp" "https://$bucket.s3.amazonaws.com/$key"
  want=$(shasum -a 256 "$file" | cut -d' ' -f1)
  got=$(shasum -a 256 "$tmp" | cut -d' ' -f1)
  [ "$want" = "$got" ] || { echo "served bytes differ for $key" >&2; exit 1; }
  echo "$bucket.s3.amazonaws.com $key $(wc -c < "$file" | tr -d ' ') $want"
done
