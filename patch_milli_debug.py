from pathlib import Path

p = Path("./adapters/miligold/client.py")

s = p.read_text(encoding="utf-8")

old = '''        data = r.json()

        if data.get("code") != 0:
            raise Exception(data)

        return data


    def confirm_trade'''

new = '''        data = r.json()

        print("MILLI INIT RESPONSE:", data)

        if data.get("code") != 0:
            raise Exception(data)

        return data


    def confirm_trade'''

if old not in s:
    raise Exception("target not found")

p.write_text(
    s.replace(old,new),
    encoding="utf-8"
)

print("DONE")
