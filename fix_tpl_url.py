from pathlib import Path

p = Path("backend/app/services/vast_admin.py")
t = p.read_text(encoding="utf-8").replace("\r\n", "\n")

# Jangan bekukan URL sementara ke template (kedaluwarsa -> 410).
count = 0
old = '    env = build_worker_env()\n    env.pop("CLIPZI_TASK_ID", None)'
new = '''    env = build_worker_env()
    env.pop("CLIPZI_TASK_ID", None)
    # URL model bertanda tangan (Dropbox/S3) kedaluwarsa; jangan dibekukan di
    # template. Nilai segar dikirim per instance saat dispatch.
    env.pop("CLIPZI_MODEL_URL", None)
    env.pop("CLIPZI_MODEL_URL_ERROR", None)'''
while old in t:
    t = t.replace(old, new, 1)
    count += 1
assert count >= 2, count
p.write_text(t, encoding="utf-8", newline="\n")
print("template env tidak membekukan URL; occurrences:", count)
