import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )

response = {
    "code": 0,
    "message": "عملیات با موفقیت انجام شد.",
    "data": {
        "invoiceStatus": "DONE"
    }
}

print(
    json.dumps(
        response,
        ensure_ascii=True,
        default=str
    )
)

print("UNICODE LOG TEST PASSED")
