import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key_str = os.getenv("YANDEX_API_KEY", "")
folder_id = os.getenv("YANDEX_FOLDER_ID", "")

print("=" * 50)
print("🧪 ТЕСТ YANDEX CLOUD AI")
print("=" * 50)

if not api_key_str:
	print("❌ YANDEX_API_KEY не найден в .env")
	exit(1)

if not folder_id:
	print("❌ YANDEX_FOLDER_ID не найден в .env")
	exit(1)

# Парсим ключ
try:
	api_key_data = json.loads(api_key_str)
	print(f"✅ Ключ в JSON формате")
	print(f"   ID ключа: {api_key_data.get('id')}")
	print(f"   Сервисный аккаунт: {api_key_data.get('service_account_id')}")

	# Для Yandex API нужен IAM токен, а не ключ JSON
	print("\n⚠️  ВНИМАНИЕ: Нужен IAM-токен, а не JSON ключ!")
	print("💡 Получи токен командой: yc iam create-token")

	# Автоматически получаем токен через CLI
	import subprocess

	try:
		print("\n🔄 Пробую получить IAM-токен автоматически...")
		result = subprocess.run(["yc", "iam", "create-token"],
		                        capture_output=True, text=True, timeout=5)
		if result.returncode == 0:
			iam_token = result.stdout.strip()
			print(f"✅ Получен IAM-токен: {iam_token[:30]}...")
			api_key = iam_token
		else:
			print(f"❌ Не удалось получить токен: {result.stderr}")
			api_key = api_key_str
	except:
		print("❌ Не удалось выполнить yc команду")
		api_key = api_key_str

except json.JSONDecodeError:
	print(f"✅ Ключ в строковом формате (предположительно IAM токен)")
	api_key = api_key_str

print(f"\n📁 Каталог: {folder_id}")

# Тестируем API
url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
headers = {
	"Authorization": f"Bearer {api_key}",
	"Content-Type": "application/json",
	"x-folder-id": folder_id
}

data = {
	"modelUri": f"gpt://{folder_id}/yandexgpt/latest",
	"completionOptions": {
		"stream": False,
		"temperature": 0.5,
		"maxTokens": 10
	},
	"messages": [
		{"role": "user", "content": "Тест"}
	]
}

print(f"\n🔍 Отправляю тестовый запрос...")
try:
	response = requests.post(url, json=data, headers=headers, timeout=10)
	print(f"📡 Статус ответа: {response.status_code}")

	if response.status_code == 200:
		result = response.json()
		text = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
		print(f"✅ УСПЕХ! API работает!")
		print(f"   Ответ: {text}")
	else:
		print(f"❌ Ошибка: {response.text[:300]}")

		# Анализ ошибки
		error_text = response.text.lower()
		if "permission" in error_text and "role" in error_text:
			print("\n🚨 ПРОБЛЕМА: Нет прав у сервисного аккаунта!")
			print("💡 Решение: Назначь роль командой:")
			print(f"yc resource-manager folder add-access-binding {folder_id} \\")
			print("  --role ai.languageModels.user \\")
			print("  --subject serviceAccount:ajejj1lr2plf060t2t92")

		elif "invalid" in error_text and "authentication" in error_text:
			print("\n🚨 ПРОБЛЕМА: Неверный ключ или токен!")
			print("💡 Решение: Получи новый IAM-токен:")
			print("1. Выполни: yc iam create-token")
			print("2. Скопируй токен (начинается с t1.)")
			print("3. Вставь в .env как YANDEX_API_KEY")

		elif "folder" in error_text and "not found" in error_text:
			print("\n🚨 ПРОБЛЕМА: Каталог не найден!")
			print("💡 Решение: Проверь YANDEX_FOLDER_ID")

except requests.exceptions.RequestException as e:
	print(f"❌ Ошибка сети: {e}")