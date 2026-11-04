"""Interactive, bounded Discord bot-to-bot relay. Never use a user token."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

HELP = """Команды консоли:
/ask ТЕКСТ       — бот отправит текстовую команду /ask выбранному боту.
/think ТЕКСТ     — бот отправит /think, пометит публичный ответ как «ДУМАЕТ»,
                   затем отправлять «продолжай» (в пределах /rounds).
/rounds N        — число автоматических продолжений для /think (0–10).
/continue ТЕКСТ  — изменить текст автоматического продолжения.
/prompt ТЕКСТ    — префикс-инструкция перед каждым новым запросом.
/prompt off      — убрать префикс (не применяется к «продолжай»).
/help           — показать команды.
/quit           — выйти.
Обычный текст работает как /ask. Ctrl+C — выход.
Ожидается одно сообщение-ответ на каждый запрос. Программа не читает
скрытые рассуждения: «ДУМАЕТ» — лишь метка режима для публичного текста.
"""


@dataclass
class Settings:
    rounds: int = 1
    continuation: str = "продолжай"
    prompt: str = ""
    timeout: float = 90.0


def parse_request(line: str) -> tuple[str, str]:
    line = line.strip()
    if not line:
        return "", ""
    if not line.startswith("/"):
        return "ask", line
    command, _, value = line.partition(" ")
    return command[1:].lower(), value.strip()


def request_text(settings: Settings, text: str) -> str:
    return f"{settings.prompt}\n\n{text}" if settings.prompt else text


def outgoing_request(settings: Settings, command: str, text: str) -> str:
    """Keep the target bot's textual command before the optional instruction."""
    if command not in ("ask", "think"):
        raise ValueError("Допустимы только /ask и /think")
    return f"/{command} {request_text(settings, text)}"


def response_text(message) -> str:
    parts = [message.content] if message.content else []
    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title)
        if embed.description:
            parts.append(embed.description)
        for field in embed.fields:
            parts.append(f"{field.name}: {field.value}")
    parts.extend(attachment.url for attachment in message.attachments)
    return "\n".join(parts) or "[Ответ без доступного текста]"


async def console(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


def positive_id(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError("ID должен быть положительным числом")
    return number


def main() -> None:
    try:
        import discord
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
    except ImportError:
        raise SystemExit("Установите зависимости: python -m pip install -r requirements.txt")

    terminal = Console()

    def print(message="", **kwargs):
        # Treat bot replies and errors as plain text, never terminal markup.
        terminal.print(Text(str(message)))

    def panel(text, title, color="cyan"):
        terminal.print(Panel(Text(str(text)), title=Text(title), border_style=color))

    panel("DISCORD  /  BOT RELAY\nТекстовые команды • ответы • продолжения", "RELAY CONSOLE", "bright_magenta")
    print("Внимание: токен при вводе виден на экране. Не показывайте окно другим.")
    token = os.getenv("DISCORD_BOT_TOKEN") or terminal.input("Токен БОТА (видимый ввод): ")
    if not token.strip():
        raise SystemExit("Токен не указан.")
    try:
        channel_id = positive_id(terminal.input("ID текстового канала: ").strip())
    except ValueError:
        raise SystemExit("Некорректный ID канала.")
    target = terminal.input("ID или точное имя другого бота: ").strip()
    if not target:
        raise SystemExit("Укажите бота.")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    client = discord.Client(intents=intents)
    settings = Settings()
    started = False

    async def exchange(channel, target_bot, text: str):
        if len(text) > 2000:
            raise ValueError("Сообщение длиннее лимита Discord (2000 символов). Сократите запрос/промпт.")
        # Register before sending so a fast answer cannot race the listener.
        sent_id = None
        early_messages = []
        # discord.Client does not provide Bot.add_listener; wait_for registers
        # a listener immediately when its coroutine is scheduled below.
        def check(message):
            if message.channel.id != channel.id or message.author.id != target_bot.id:
                return False
            if sent_id is None:
                early_messages.append(message)
                return False
            return message.id > sent_id

        waiter = asyncio.create_task(client.wait_for("message", check=check, timeout=settings.timeout))
        try:
            await asyncio.sleep(0)
            if len(text) + len(target_bot.mention) + 1 > 2000:
                raise ValueError("Запрос вместе с упоминанием превышает 2000 символов.")
            sent = await channel.send(f"{target_bot.mention} {text}", allowed_mentions=discord.AllowedMentions(users=[target_bot], roles=False, everyone=False))
            sent_id = sent.id
            for message in early_messages:
                if message.id > sent_id:
                    return message
            return await waiter
        finally:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)

    async def run_console():
        channel = await client.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("Нужен текстовый канал сервера, не ЛС или форум.")
        if target.isdecimal():
            target_bot = await channel.guild.fetch_member(positive_id(target))
        else:
            members = [member async for member in channel.guild.fetch_members(limit=None)]
            matches = [m for m in members if m.bot and target in (m.name, m.display_name, str(m))]
            if len(matches) != 1:
                raise ValueError("Имя не найдено или неоднозначно. Перезапустите программу и укажите ID бота.")
            target_bot = matches[0]
        if not target_bot.bot or target_bot.id == client.user.id:
            raise ValueError("Выберите другого бота, а не себя или пользователя.")
        panel(f"Аккаунт: {client.user}\nКанал: #{channel.name}\nЦелевой бот: {target_bot}", "ПОДКЛЮЧЕНО", "green")
        print("Не запускайте встречные реле. Работайте только в разрешённом канале.")
        panel(HELP, "КОМАНДЫ")
        while not client.is_closed():
            command, value = parse_request(await console("relay › "))
            if not command:
                continue
            if command == "quit":
                return
            if command == "help":
                panel(HELP, "КОМАНДЫ")
            elif command == "rounds":
                try:
                    number = int(value)
                    if not 0 <= number <= 10:
                        raise ValueError
                    settings.rounds = number
                    print(f"Автоматических продолжений: {number}")
                except ValueError:
                    print("Используйте /rounds N, где N от 0 до 10.")
            elif command == "continue":
                if not value or len(value) > 1500:
                    print("Нужен текст длиной от 1 до 1500 символов.")
                else:
                    settings.continuation = value
                    print("Текст продолжения сохранён.")
            elif command == "prompt":
                settings.prompt = "" if value == "off" else value
                print("Промпт обновлён.")
            elif command in ("ask", "think"):
                if not value:
                    print("После команды нужен текст запроса.")
                    continue
                try:
                    text = outgoing_request(settings, command, value)
                    count = settings.rounds if command == "think" else 0
                    for turn in range(count + 1):
                        if turn:
                            await asyncio.sleep(2)
                            text = settings.continuation
                            print(f"[ПРОДОЛЖЕНИЕ {turn}/{count}] {text}")
                        panel(text, "БОТ → DISCORD", "blue")
                        with terminal.status("Ожидаем ответ выбранного бота…", spinner="dots"):
                            answer = await exchange(channel, target_bot, text)
                        label = "ДУМАЕТ · публичный ответ" if command == "think" else "ОТВЕТ"
                        panel(response_text(answer), label, "yellow" if command == "think" else "green")
                except asyncio.TimeoutError:
                    print("Ответ не получен за 90 секунд. Цепочка остановлена. Бот может игнорировать других ботов.")
                except (discord.HTTPException, ValueError) as error:
                    print(f"Цепочка остановлена: {error}")
            else:
                print("Неизвестная команда. Список: /help")

    @client.event
    async def on_ready():
        nonlocal started
        if started:
            return
        started = True
        try:
            await run_console()
        except (EOFError, asyncio.CancelledError):
            pass
        except (discord.DiscordException, ValueError) as error:
            print(f"Ошибка: {error}")
        finally:
            await client.close()

    try:
        client.run(token.strip(), log_level=30)
    except discord.LoginFailure:
        print("Неверный токен бота. Проверьте его в Discord Developer Portal.")
    except discord.PrivilegedIntentsRequired:
        print("Включите Message Content Intent и Server Members Intent в Developer Portal → Bot.")
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
