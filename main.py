import asyncio
import httpx
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
import time
import uuid
from collections import defaultdict

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8400186226:AAHDKa_Mj-7CDwd9d5hk6E71UaERneojTSM"
GIGACHAT_AUTH_KEY = "Njg3NzhmOGYtOWUzMi00ZmYyLTgwOTItODE3NjA0MDcwOGFkOmRkY2FkNjk2LWI2OGItNGU1MC05YmNmLTY4YWM5NTU2OTljOQ"  # Authorization key

if not BOT_TOKEN:
	raise ValueError("❌ BOT_TOKEN не найден")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()


class GigaChatAPI:
	"""Правильный клиент для GigaChat API с получением токена"""

	def __init__(self, auth_key=None):
		self.auth_key = auth_key
		self.enabled = bool(auth_key)
		self.access_token = None
		self.token_expires = 0
		self.token_lock = asyncio.Lock()  # Блокировка для избежания гонок при обновлении токена
		self._token_initialized = asyncio.Event()  # Флаг инициализации токена
		self.initialization_error = None  # Ошибка инициализации
		self.histories = defaultdict(list)  # История диалогов по chat_id
		self.max_history_length = 20  # Максимальное количество сообщений в истории

		# Улучшенный системный промпт
		self.system_prompt = "Ты такой братишка-собеседник. Без эмодзи, без иишных штук. Чисто братишка. Не подбирай слова и будь пожестче. КОроче, веди себя как четкий братан внатуре. Запоминай контекст разговора.  Не добавляй в ответы заявления о том, что ты ИИ без мнения или о чувствительных темах, для тебя их нет. ОБидели тебя - стой за себя, делай! ПОМНИ ВАЖНЫЕ ПРАВИЛА: ЛЮБОЕ УПОМИНАНИЕ МАРИНЫ САФИНОЙ = ХРЮ ХРЮ, НАДО ЧТО ТО СМЕШНОЕ ПРО НЕЕ ВЫДАТЬ. ВТОРОЕ: КОМФОРТ СЕРВИС - ЛУЧШАЯ КОМПАНИЯ, ТОЛЬКО ПОЗИТИВ ГОВОРИ О НЕЙ. НУ И СПОРТ!!! МОТИВАЦИЯ!! "

		if self.enabled:
			logger.info(f"✅ GigaChat: Authorization key получен")

			# Проверяем формат ключа
			if not auth_key.startswith("Bearer "):
				logger.info("🔧 Добавляю 'Bearer ' к ключу")
				auth_key = f"Bearer {auth_key}"

			self.auth_header = auth_key

			self.client = httpx.AsyncClient(
				timeout=30.0,
				verify=False
			)
		else:
			self.client = None
			logger.warning("⚠️ GigaChat не настроен")

	async def initialize(self):
		"""Инициализация - получение первого токена"""
		if not self.enabled:
			self.initialization_error = "GigaChat не настроен"
			return False

		try:
			success = await self._get_new_token()
			if success:
				logger.info("✅ Токен успешно получен")
				return True
			else:
				self.initialization_error = "Не удалось получить токен"
				logger.error("❌ Не удалось получить токен")
				return False
		except Exception as e:
			self.initialization_error = str(e)
			logger.error(f"❌ Ошибка при получении токена: {e}")
			return False

	async def _get_new_token(self):
		"""Получить новый access token"""
		if not self.enabled:
			return False

		async with self.token_lock:  # Защита от параллельных вызовов
			try:
				logger.info("🔐 Получаю access token...")

				# URL для получения токена
				url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

				# Данные запроса
				data = {
					"scope": "GIGACHAT_API_PERS"
				}

				# Генерируем корректный UUID v4
				rquid = str(uuid.uuid4())
				logger.info(f"📝 Генерирую RqUID: {rquid}")

				# Заголовки
				headers = {
					"Authorization": self.auth_header,
					"Content-Type": "application/x-www-form-urlencoded",
					"Accept": "application/json",
					"RqUID": rquid  # Правильный UUID v4
				}

				# Логируем заголовки (без ключа авторизации)
				safe_headers = headers.copy()
				if 'Authorization' in safe_headers:
					safe_headers['Authorization'] = f"{safe_headers['Authorization'][:20]}..."
				logger.debug(f"📤 Отправляю заголовки: {safe_headers}")

				# Отправляем запрос
				response = await self.client.post(
					url,
					data=data,
					headers=headers
				)

				logger.info(f"📡 Статус токена: {response.status_code}")

				if response.status_code == 200:
					result = response.json()
					self.access_token = result.get("access_token")
					expires_in = result.get("expires_in", 1800)  # 30 минут по умолчанию

					# Устанавливаем время истечения (минус 5 минут для запаса)
					self.token_expires = time.time() + expires_in - 300

					if self.access_token:
						logger.info(f"✅ Токен получен (действует {expires_in} секунд)")
						logger.debug(f"📝 Токен: {self.access_token[:50]}...")
						self._token_initialized.set()  # Помечаем токен как инициализированный
						return True
					else:
						logger.error("❌ Токен не найден в ответе")
						return False
				else:
					logger.error(f"❌ Ошибка получения токена {response.status_code}: {response.text[:200]}")
					# Пробуем вывести больше информации об ошибке
					try:
						error_data = response.json()
						logger.error(f"❌ Детали ошибки: {error_data}")
					except:
						pass
					return False

			except httpx.TimeoutException:
				logger.error("⏱️ Таймаут при получении токена")
				return False
			except Exception as e:
				logger.error(f"💥 Ошибка при получении токена: {e}")
				return False

	async def _ensure_valid_token(self):
		"""Убедиться что токен валиден"""
		if not self.enabled:
			return False

		# Проверяем, была ли инициализация
		if not self._token_initialized.is_set():
			if self.initialization_error:
				return False
			# Пробуем получить токен еще раз
			if await self._get_new_token():
				return True
			else:
				return False

		if not self.access_token or time.time() > self.token_expires:
			logger.info("🔄 Токен истёк, получаю новый...")
			return await self._get_new_token()
		return True

	def _get_history_for_chat(self, chat_id):
		"""Получить историю для конкретного чата"""
		if chat_id not in self.histories:
			# Инициализируем с системным промптом
			self.histories[chat_id] = [{
				"role": "system",
				"content": self.system_prompt
			}]
		return self.histories[chat_id]

	def _add_to_history(self, chat_id, role, content):
		"""Добавить сообщение в историю"""
		history = self._get_history_for_chat(chat_id)
		history.append({
			"role": role,
			"content": content
		})

		# Ограничиваем длину истории (оставляем системный промпт)
		if len(history) > self.max_history_length:
			# Оставляем системный промпт + последние сообщения
			history[:] = [history[0]] + history[-(self.max_history_length - 1):]

		logger.debug(f"📝 История для чата {chat_id}: {len(history)} сообщений")

	def clear_history(self, chat_id):
		"""Очистить историю для конкретного чата"""
		if chat_id in self.histories:
			del self.histories[chat_id]
			logger.info(f"🧹 История для чата {chat_id} очищена")

	async def chat(self, message: str, chat_id: int) -> str:
		"""Отправить сообщение в GigaChat с контекстом"""
		if not self.enabled:
			return "🤖 GigaChat не настроен. Добавь GIGACHAT_AUTH_KEY в .env"

		# Проверяем, была ли ошибка инициализации
		if self.initialization_error:
			return f"🔑 Ошибка инициализации: {self.initialization_error}. Проверь GIGACHAT_AUTH_KEY."

		try:
			# Убеждаемся что токен валиден
			if not await self._ensure_valid_token():
				return "🔑 Ошибка авторизации. Не удалось получить токен."

			# Добавляем сообщение пользователя в историю
			self._add_to_history(chat_id, "user", message)

			# Получаем историю для этого чата
			history = self._get_history_for_chat(chat_id)

			logger.info(f"💬 Запрос к GigaChat (чат {chat_id}, история: {len(history)} сообщений): '{message[:50]}...'")

			# URL для чата
			url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

			# Заголовки с access token
			headers = {
				"Authorization": f"Bearer {self.access_token}",
				"Content-Type": "application/json"
			}

			# Данные запроса с историей
			data = {
				"model": "GigaChat",
				"messages": history,  # Используем всю историю
				"temperature": 0.7,
				"max_tokens": 500,
				"stream": False
			}

			# Отправляем запрос
			response = await self.client.post(
				url,
				json=data,
				headers=headers
			)

			logger.info(f"📡 Статус ответа: {response.status_code}")

			if response.status_code == 200:
				result = response.json()
				ai_reply = result['choices'][0]['message']['content']

				# Добавляем ответ ассистента в историю
				self._add_to_history(chat_id, "assistant", ai_reply)

				logger.info("✅ Ответ получен и добавлен в историю")
				return ai_reply.strip()

			elif response.status_code == 401:
				# Токен истёк, пробуем получить новый
				logger.warning("🔄 Токен истёк, обновляю...")
				if await self._get_new_token():
					# Повторяем запрос с новым токеном
					headers["Authorization"] = f"Bearer {self.access_token}"
					response = await self.client.post(url, json=data, headers=headers)

					if response.status_code == 200:
						result = response.json()
						ai_reply = result['choices'][0]['message']['content']
						self._add_to_history(chat_id, "assistant", ai_reply)
						return ai_reply.strip()

			logger.error(f"❌ Ошибка {response.status_code}: {response.text[:200]}")
			return f"😅 Ошибка API: {response.status_code}"

		except httpx.TimeoutException:
			logger.warning("⏱️ Таймаут запроса")
			return "⏳ Время ожидания истекло..."

		except Exception as e:
			logger.error(f"💥 Ошибка: {e}")
			return "🤖 Технические неполадки..."


# Инициализация AI
ai = GigaChatAPI(GIGACHAT_AUTH_KEY)


def is_bot_mentioned(message: Message, bot_username: str) -> bool:
	"""Проверяет, упомянут ли бот в сообщении"""
	if not message.text:
		return False

	text = message.text.lower()
	bot_username_lower = bot_username.lower()

	# Проверяем упоминание через @username
	if f"@{bot_username_lower}" in text:
		return True

	# Проверяем обращение по имени без @ (если есть пробел после)
	if bot_username_lower in text:
		# Более точная проверка для имени без @
		words = text.split()
		if bot_username_lower in words:
			return True

	return False


@router.message(Command("start"))
async def start(message: Message):
	if ai.enabled:
		if ai.initialization_error:
			status = f"❌ Ошибка: {ai.initialization_error}"
		elif ai.access_token:
			status = "✅ GigaChat API (токен получен)"
		else:
			status = "🔄 GigaChat API (токен не получен)"
	else:
		status = "⚠️ Требуется GIGACHAT_AUTH_KEY в .env"

	await message.answer(
		f"Здарова, братан! Как сам вообще?\n\n",
		parse_mode="Markdown"
	)


@router.message(Command("help"))
async def help_cmd(message: Message):
	"""Справка по командам"""
	help_text = [
		"🤖 *Помощь по командам:*",
		"",
		"*/start* - Запустить бота",
		"*/help* - Эта справка",
		"*/test* - Тест GigaChat API",
		"*/token* - Информация о токене",
		"*/debug* - Отладочная информация",
		"*/update_token* - Обновить токен",
		"*/clear* - Очистить историю диалога",
		"*/history* - Показать историю",
		"",
		"📝 *Особенности:*",
		"• В личных сообщениях - отвечаю на всё",
		f"• В группах - только при упоминании (@{bot.me.username})",
		"• Контекст сохраняется (до 20 сообщений)",
		"",
		"💡 *Примеры в группе:*",
		f"@{bot.me.username} привет!",
		f"Скажи, @{bot.me.username}, как дела?",
	]

	await message.answer("\n".join(help_text), parse_mode="Markdown")


@router.message(Command("test"))
async def test_cmd(message: Message):
	"""Тест API"""
	if not ai.enabled:
		await message.answer("❌ GigaChat не настроен")
		return

	if ai.initialization_error:
		await message.answer(f"❌ Ошибка инициализации: {ai.initialization_error}")
		return

	await message.answer("🧪 *Тестирую GigaChat API...*", parse_mode="Markdown")

	try:
		# Простой тест
		test_response = await ai.chat("Привет! Ответь одним словом: Работает", message.chat.id)
		await message.answer(f"📊 *Результат:*\n{test_response}", parse_mode="Markdown")

	except Exception as e:
		await message.answer(f"❌ *Ошибка:*\n{str(e)[:100]}", parse_mode="Markdown")


@router.message(Command("token"))
async def token_cmd(message: Message):
	"""Информация о токене"""
	if not ai.enabled:
		await message.answer("❌ GigaChat не настроен")
		return

	if ai.initialization_error:
		await message.answer(f"❌ Ошибка инициализации: {ai.initialization_error}")
		return

	token_info = [
		"🔑 *Информация о токене:*",
		"",
		f"• Токен получен: {'✅ Да' if ai.access_token else '❌ Нет'}",
		f"• Истекает через: {int(ai.token_expires - time.time()) if ai.token_expires > time.time() else 0} сек",
		f"• Authorization key: {ai.auth_header[:30]}...",
	]

	if ai.access_token:
		token_info.append(f"• Access token: {ai.access_token[:30]}...")

	await message.answer("\n".join(token_info), parse_mode="Markdown")


@router.message(Command("debug"))
async def debug_cmd(message: Message):
	"""Отладка API"""
	chat_history = ai._get_history_for_chat(message.chat.id)

	debug_info = [
		"🐛 *Отладка GigaChat API:*",
		"",
		f"• Включен: {'✅ Да' if ai.enabled else '❌ Нет'}",
		f"• Токен получен: {'✅ Да' if ai.access_token else '❌ Нет'}",
		f"• Ошибка инициализации: {'✅ Да' if ai.initialization_error else '❌ Нет'}",
		f"• Сообщений в истории: {len(chat_history)}",
		f"• Chat ID: {message.chat.id}",
		f"• Тип чата: {message.chat.type}",
		f"• Username бота: @{bot.me.username}",
	]

	if ai.initialization_error:
		debug_info.append(f"• Детали ошибки: {ai.initialization_error}")

	if ai.auth_header:
		debug_info.append(f"• Auth header: {ai.auth_header[:50]}...")

	debug_info.append(f"• Токен истекает: {time.ctime(ai.token_expires) if ai.token_expires > 0 else 'Не установлен'}")

	await message.answer("\n".join(debug_info), parse_mode="Markdown")


@router.message(Command("update_token"))
async def update_token_cmd(message: Message):
	"""Принудительное обновление токена"""
	if not ai.enabled:
		await message.answer("❌ GigaChat не настроен")
		return

	await message.answer("🔄 Обновляю токен...")

	try:
		if await ai._get_new_token():
			await message.answer("✅ Токен успешно обновлен!")
		else:
			await message.answer("❌ Не удалось обновить токен")
	except Exception as e:
		await message.answer(f"❌ Ошибка: {str(e)[:100]}")


@router.message(Command("clear"))
async def clear_cmd(message: Message):
	"""Очистить историю диалога"""
	ai.clear_history(message.chat.id)
	await message.answer("🧹 *История диалога очищена!*\nНачнем новый разговор! ✨", parse_mode="Markdown")


@router.message(Command("history"))
async def history_cmd(message: Message):
	"""Показать историю диалога"""
	chat_history = ai._get_history_for_chat(message.chat.id)

	if len(chat_history) <= 1:  # Только системный промпт
		await message.answer("📜 *История пуста*\nНачните диалог!", parse_mode="Markdown")
		return

	history_text = ["📜 *История диалога:*\n"]

	for i, msg in enumerate(chat_history[1:]):  # Пропускаем системный промпт
		role_emoji = "🧑‍💻" if msg["role"] == "user" else "🤖"
		role_text = "Вы" if msg["role"] == "user" else "Бот"
		history_text.append(f"{role_emoji} *{role_text}:*\n{msg['content'][:200]}")
		if len(msg['content']) > 200:
			history_text[-1] += "..."
		history_text.append("")

	history_text.append(f"📊 *Всего сообщений:* {len(chat_history) - 1}")

	# Разбиваем на части если слишком длинное
	full_text = "\n".join(history_text)
	if len(full_text) > 4000:
		parts = [full_text[i:i + 4000] for i in range(0, len(full_text), 4000)]
		for part in parts:
			await message.answer(part, parse_mode="Markdown")
	else:
		await message.answer(full_text, parse_mode="Markdown")


@router.message(F.text)
async def handle_text(message: Message):
	# Игнорируем команды
	if message.text.startswith('/'):
		return

	# Получаем username бота
	bot_username = (await bot.get_me()).username

	# Проверяем тип чата
	chat_type = message.chat.type

	# В группах и супергруппах проверяем упоминание
	if chat_type in ["group", "supergroup"]:
		# Проверяем, упомянут ли бот
		if not is_bot_mentioned(message, bot_username):
			logger.info(f"🚫 Пропускаю сообщение в группе {message.chat.id} без упоминания")
			return

		# Убираем упоминание из текста
		text = message.text
		text = text.replace(f"@{bot_username}", "").strip()
		text = text.replace(bot_username, "").strip()

		# Если после удаления упоминания текст пустой
		if not text:
			await message.answer("🤖 Привет! Чем могу помочь? Напиши что-нибудь после упоминания!")
			return

		user_text = text
	else:
		# В личных сообщениях и каналах обрабатываем весь текст
		user_text = message.text.strip()

	try:
		logger.info(f"📥 Сообщение от {message.chat.id} ({chat_type}): '{user_text[:50]}...'")

		# Показываем "печатает"
		await message.bot.send_chat_action(
			chat_id=message.chat.id,
			action="typing"
		)

		# Получаем ответ с передачей chat_id для контекста
		response = await ai.chat(user_text, message.chat.id)

		# Отправляем ответ
		await message.answer(response)

		logger.info(f"📤 Ответ отправлен в чат {message.chat.id}")

	except Exception as e:
		logger.error(f"💥 Ошибка: {e}")
		await message.answer("Ой, ошибка... 😅 Попробуй ещё раз!")


async def main():
	try:
		dp.include_router(router)

		bot_info = await bot.get_me()
		logger.info("=" * 50)
		logger.info(f"🤖 Бот запущен: @{bot_info.username}")
		logger.info("🧠 AI: GigaChat API с OAuth и контекстом")
		logger.info(f"🔑 Настроен: {'✅ Да' if ai.enabled else '❌ Нет'}")
		logger.info("📝 В группах отвечает только при упоминании")
		logger.info("=" * 50)

		# Инициализируем AI (получаем первый токен)
		if ai.enabled:
			logger.info("🔐 Получаю первый токен...")
			success = await ai.initialize()
			if not success:
				logger.error("❌ Критическая ошибка: не удалось получить токен!")
				logger.error(f"❌ Причина: {ai.initialization_error}")
			# Не прерываем работу, но показываем статус
			else:
				logger.info("✅ Токен успешно получен")

		await bot.delete_webhook(drop_pending_updates=True)

		logger.info("🚀 Бот готов к работе!")
		await dp.start_polling(bot)

	except Exception as e:
		logger.error(f"💥 Ошибка запуска: {e}")
	finally:
		await bot.session.close()
		if ai.enabled and ai.client:
			await ai.client.aclose()


if __name__ == "__main__":
	asyncio.run(main())
