import re
import requests
import time
import json
import os
import sys
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

TOKEN = os.environ.get("TOKEN")
REPO = os.environ.get("REPO")
WORKFLOW = "fetch.yml"


def trigger_workflow():
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    data = {"ref": "main"}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 204:
        print("工作流触发成功")
    else:
        print(f"触发工作流失败，状态码：{response.status_code}")


def get_lasted_user_id():
    url = "https://greasyfork.org/en/users"
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        # 使用正则表达式来提取用户 ID
        match = re.search(r'users/(\d+)-', response.text)
        if match:
            return int(match.group(1))
        else:
            print("未找到用户 ID")
            return 0
    else:
        print(f"获取最后注册用户失败，状态码：{response.status_code}")
        return 0


def get_created_at(user_id):
    url = f"https://api.greasyfork.org/users/{user_id}.json"
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        data = response.json()
        return data.get('created_at', None)
    else:
        return response.status_code


def push_(commit_message, json_data):
    with open("users_created_time.json", "w") as f:
        json.dump(json_data, f, indent=4)
    os.system("git add .")
    os.system(f"git commit -m '{commit_message}'")
    os.system("git push")


def get_last_valid_user_id():
    if os.path.exists("users_created_time.json") and os.path.getsize("users_created_time.json") > 0:
        with open("users_created_time.json", "r") as f:
            data = json.load(f)
        if data:
            return max(map(int, data.keys()))
    return 0


def parse_timestamp(created_at):
    if isinstance(created_at, int):
        return created_at
    return int(datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())


def fetch_user_creation_time(user_id):
    created_at = get_created_at(user_id)
    if created_at:
        try:
            timestamp = parse_timestamp(created_at)
        except ValueError:
            timestamp = int(created_at)
        return user_id, timestamp
    else:
        return user_id, None


def main(threads):
    num_iterations = 50
    max_runs = 20000
    lasted_reg_id = get_lasted_user_id()
    start_time = time.time()
    print(f"最后注册的ID是：[{lasted_reg_id}]")

    for run in range(1, max_runs + 1):
        print(f"当前正在运行第：（{run}/{max_runs}）")
        json_output = {}
        if os.path.exists("users_created_time.json"):
            with open("users_created_time.json", "r") as f:
                json_output = json.load(f)

        last_valid_user_id = get_last_valid_user_id()
        next_user_id = last_valid_user_id + 1

        with ThreadPoolExecutor(max_workers=threads) as executor:
            future_to_user_id = {
                executor.submit(fetch_user_creation_time, user_id): user_id
                for user_id in range(next_user_id, next_user_id + num_iterations)
            }

            for future in future_to_user_id:
                user_id, created_at = future.result()
                if created_at:
                    json_output[str(user_id)] = created_at
                    print(f"{user_id} 的创建时间为：{created_at}")
                else:
                    print(f"用户 {user_id} 的创建时间未找到或为空")

        # 检查是否需要重启
        elapsed_time = time.time() - start_time
        if elapsed_time > 18000:
            print("重新启动...")
            push_("重启工作流", json_output)
            time.sleep(10)
            trigger_workflow()
            sys.exit()

        if next_user_id + num_iterations > lasted_reg_id:
            print(f"现行用户ID超过最后注册的ID [{lasted_reg_id}], 退出脚本")
            push_(f"现行用户超过最后注册的ID [{lasted_reg_id}]", json_output)
            sys.exit()

        push_("更新", json_output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="控制并发线程数量")
    parser.add_argument('--threads', type=int, default=10,
                        help="设置并发线程的数")
    args = parser.parse_args()
    main(args.threads)
