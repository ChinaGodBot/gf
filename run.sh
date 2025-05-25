#!/bin/bash


trigger_workflow() {
  local branch="main"
  local workflow="fetch.yml"
  curl -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches \
    -d "{\"ref\": \"${branch}\"}"
}

#获取最后注册用户
get_lasted_user_id() {
    local url="https://greasyfork.org/en/users"
    local page_content=$(curl -s "$url")
    local first_match=$(echo "$page_content" | grep -oP 'users/\d+-' | head -n 1)
    local user_id=$(echo "$first_match" | grep -oP '(?<=users/)\d+')
    echo "$user_id"
}


get_created_at() {
  local user_id=$1
  local api_url="https://api.greasyfork.org/users/${user_id}.json"
  local response=$(curl -sL -w "%{http_code}" "$api_url" -o response.json)
  local http_code=${response: -3}

  if [ "$http_code" -ne 200 ]; then
    echo "$http_code"
    return
  fi

  local created_at=$(jq -r '.created_at' response.json)
  echo "$created_at"
  rm -f response.json
}

push_() {
  local commit_message="$1"
  local json_data="$2"
  echo "$json_data" | jq . > users_created_time.json
  git add .
  git commit -m "$commit_message"
  git push
}

# 获取json内最后一个有效用户 ID
get_last_valid_user_id() {
  if [ -f "users_created_time.json" ] && [ -s "users_created_time.json" ]; then
    last_valid_user_id=$(jq -r 'keys | map(tonumber) | max' users_created_time.json 2>/dev/null)
    if [ "$last_valid_user_id" == "null" ] || [ -z "$last_valid_user_id" ]; then
      echo "0"
    else
      echo "$last_valid_user_id"
    fi
  else
    echo "0"
  fi
}

# 定义循环次数和总的执行次数
num_iterations=50    # 设置每次循环查询的用户数
max_runs=20000          # 设置脚本运行的最大次
lasted_reg_id=$(get_lasted_user_id)
start_time=$(date +%s)
echo "最后注册的ID是： [$lasted_reg_id]"

for run in $(seq 1 $max_runs); do
  echo "当前正在运行运行第：（$run/$max_runs）"
  if [ -f "users_created_time.json" ]; then
    json_output=$(cat users_created_time.json)
  else
    json_output="{}"
  fi
  
  # 最后一个有效用户 ID(不要获取json长度，有的id根本不存在)
  last_valid_user_id=$(get_last_valid_user_id)

  # +1等于下一个用户 ID
  next_user_id=$((last_valid_user_id + 1))

  # 循环 $num_iterations 次
  for user_id in $(seq $next_user_id $((next_user_id + num_iterations - 1))); do
    end_time=$(date +%s)
    elapsed_time=$((end_time - start_time)) # 计算时间差
     if [ $elapsed_time -gt 18000 ]; then
       echo "重新启动..."
       push_ "重启工作流" "$json_output"
       sleep 10
       trigger_workflow
       break 2
     fi
    if [ "$user_id" -gt $lasted_reg_id ]; then
      echo "现行用户ID: $user_id 超过最后注册的ID: [$lasted_reg_id],退出脚本"
      push_ "现行用户超过最后注册的ID [$lasted_reg_id]" "$json_output"
      break 2
    fi
    created_at=$(get_created_at "$user_id")

    if [ -n "$created_at" ] && [ "$created_at" != "null" ]; then
      timestamp=$([ ${#created_at} -ge 5 ] && date -d "$created_at" +%s || echo "$created_at" | awk '{print int($1)}')
      json_output=$(echo "$json_output" | jq --arg user_id "$user_id" --argjson timestamp "$timestamp" \
    '. + {($user_id): $timestamp}')
      echo "$user_id的创建时间为：$created_at"
    else
      echo "用户 $user_id 的创建时间未找到或为空"
    fi

    #sleep 1
  done  
  push_ "更新" "$json_output"
  
done
