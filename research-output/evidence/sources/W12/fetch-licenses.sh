#!/bin/bash
echo "repo,spdx,license_path,default_branch,sha,archived,stars,pushed_at"
while read r; do
  j=$(gh api repos/$r 2>/dev/null) || { echo "$r,ERR"; continue; }
  full=$(echo "$j" | jq -r .full_name); br=$(echo "$j" | jq -r .default_branch)
  sha=$(gh api repos/$full/commits/$br --jq .sha 2>/dev/null)
  lp=$(gh api repos/$full/license --jq '.path+"|"+.license.spdx_id' 2>/dev/null || echo "none|none")
  echo "$full,${lp#*|},${lp%|*},$br,$sha,$(echo "$j" | jq -r '[.archived,.stargazers_count,.pushed_at]|map(tostring)|join(",")')"
done < repos.txt
