import ast
import json
from pathlib import Path

from adapters.goldika.client import GoldikaClient


source = Path("./live_bot.py").read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)

args = None

for node in tree.body:

    if not isinstance(node, ast.Assign):
        continue

    if not any(
        isinstance(t, ast.Name)
        and t.id == "goldika"
        for t in node.targets
    ):
        continue

    call = node.value

    if (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "GoldikaClient"
        and len(call.args) == 2
    ):
        args = [
            ast.literal_eval(x)
            for x in call.args
        ]
        break


if args is None:
    raise Exception(
        "GoldikaClient config not found"
    )


c = GoldikaClient(
    args[0],
    args[1]
)

c.login()


def scan(obj, path="root"):

    keywords = (
        "fee",
        "commission",
        "percent",
        "percentage",
        "rate",
        "wage",
        "کارمزد"
    )

    if isinstance(obj, dict):

        for key, value in obj.items():

            new_path = f"{path}.{key}"

            if any(
                word in str(key).lower()
                for word in keywords
            ):
                print(
                    new_path,
                    "=",
                    value
                )

            scan(
                value,
                new_path
            )

    elif isinstance(obj, list):

        for i, value in enumerate(obj):
            scan(
                value,
                f"{path}[{i}]"
            )


for name, url in [
    (
        "SYSTEM CONFIG",
        "/api/v1/system-config/get"
    ),
    (
        "EXCHANGE HISTORY",
        "/api/v1/exchanges?page=1"
    )
]:

    print()
    print("=" * 60)
    print(name)
    print("=" * 60)

    r = c.session.get(
        c.BASE_URL + url,
        timeout=15
    )

    print(
        "STATUS:",
        r.status_code
    )

    data = r.json()

    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        )
    )

    print()
    print("--- POSSIBLE FEE FIELDS ---")

    scan(data)


print()
print("READ ONLY - NO TRADE EXECUTED")
