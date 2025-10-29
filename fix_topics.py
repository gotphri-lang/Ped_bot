import json

with open("questions.json", encoding="utf-8") as f:
    data = json.load(f)

for q in data:
    topic = q.get("topic", "").strip()
    for sep in ["/", ",", "-", "—"]:
        if sep in topic:
            topic = topic.split(sep)[0].strip()
    q["topic"] = topic.capitalize()

data.sort(key=lambda x: x.get("topic", "").lower())

with open("questions.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

topics = sorted(set(q["topic"] for q in data))
print("✅ Темы сокращены до одного слова и отсортированы по алфавиту.\n")
print("📚 Список тем:")
for t in topics:
    print(" -", t)