from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import Any

from ....config import AppSettings
from ....integrations.telegram.bot_client import TelegramBotClient
from .access import is_settings_admin
from .service import TgBotRuntimeSettings, TgBotSettingsService, _env
from .session_login import InteractiveSessionLogin
from .session_runtime import (
    cleanup_temp_session_files,
    delete_current_session,
    install_temp_session,
    related_session_files,
    resolve_session_path,
)
from .status import build_settings_status_snapshot, perform_its_access_check
from .topics import TOPIC_EDIT_TOKEN_MAP, TOPIC_FIELD_LABELS, apply_runtime_settings_update

try:
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
except ImportError:
    CallbackQuery = Any
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
    Message = Any
    TelegramBadRequest = RuntimeError

SETTINGS_CALLBACK_PREFIX = "settings:"
CALLBACK_MAIN = f"{SETTINGS_CALLBACK_PREFIX}main"
CALLBACK_REFRESH = f"{SETTINGS_CALLBACK_PREFIX}refresh"
CALLBACK_CHECK_ACCESS = f"{SETTINGS_CALLBACK_PREFIX}check_access"
CALLBACK_DELETE_SESSION = f"{SETTINGS_CALLBACK_PREFIX}delete_session"
CALLBACK_DELETE_CONFIRM = f"{SETTINGS_CALLBACK_PREFIX}delete_confirm"
CALLBACK_DELETE_CANCEL = f"{SETTINGS_CALLBACK_PREFIX}delete_cancel"
CALLBACK_ADD_SESSION = f"{SETTINGS_CALLBACK_PREFIX}add_session"
CALLBACK_TOPICS = f"{SETTINGS_CALLBACK_PREFIX}topics"
CALLBACK_TOPICS_BACK = f"{SETTINGS_CALLBACK_PREFIX}topics_back"
CALLBACK_TOPIC_EDIT_PREFIX = f"{SETTINGS_CALLBACK_PREFIX}topic_edit:"


@dataclass
class PendingTopicEdit:
    field: str


@dataclass
class PendingSessionLogin:
    login: InteractiveSessionLogin
    step: str


def _is_bot_command(text: str | None, command: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    first_token = normalized.split(maxsplit=1)[0]
    if first_token.startswith("/"):
        first_token = first_token.split("@", 1)[0]
    return first_token == command.lower()


def _with_cancel_hint(text: str) -> str:
    return f"{text}\nДля отмены: /cancel"


def _main_keyboard() -> InlineKeyboardMarkup | None:
    if InlineKeyboardMarkup is None or InlineKeyboardButton is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверить доступ к ТГ", callback_data=CALLBACK_CHECK_ACCESS)],
            [
                InlineKeyboardButton(text="Удалить сессию", callback_data=CALLBACK_DELETE_SESSION),
                InlineKeyboardButton(text="Добавить сессию", callback_data=CALLBACK_ADD_SESSION),
            ],
            [
                InlineKeyboardButton(text="Темы", callback_data=CALLBACK_TOPICS),
                InlineKeyboardButton(text="Обновить", callback_data=CALLBACK_REFRESH),
            ],
        ]
    )


def _delete_confirm_keyboard() -> InlineKeyboardMarkup | None:
    if InlineKeyboardMarkup is None or InlineKeyboardButton is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=CALLBACK_DELETE_CONFIRM),
                InlineKeyboardButton(text="Отмена", callback_data=CALLBACK_DELETE_CANCEL),
            ]
        ]
    )


def _topics_keyboard() -> InlineKeyboardMarkup | None:
    if InlineKeyboardMarkup is None or InlineKeyboardButton is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Chat", callback_data=f"{CALLBACK_TOPIC_EDIT_PREFIX}chat"),
                InlineKeyboardButton(text="Allowed", callback_data=f"{CALLBACK_TOPIC_EDIT_PREFIX}allowed"),
            ],
            [
                InlineKeyboardButton(text="Comments", callback_data=f"{CALLBACK_TOPIC_EDIT_PREFIX}comments"),
                InlineKeyboardButton(text="Price", callback_data=f"{CALLBACK_TOPIC_EDIT_PREFIX}price"),
            ],
            [
                InlineKeyboardButton(text="Settings", callback_data=f"{CALLBACK_TOPIC_EDIT_PREFIX}settings"),
                InlineKeyboardButton(text="Suppliers", callback_data=f"{CALLBACK_TOPIC_EDIT_PREFIX}suppliers"),
            ],
            [InlineKeyboardButton(text="Назад", callback_data=CALLBACK_TOPICS_BACK)],
        ]
    )


def _format_request_comment_map(value: dict[int, int]) -> str:
    return "\n".join(f"{request} -> {comment}" for request, comment in sorted(value.items())) or "-"


def _format_supplier_topic_map(value: dict[str, int]) -> str:
    return "\n".join(f"{supplier} -> {topic}" for supplier, topic in sorted(value.items())) or "-"


def _format_status_card(snapshot: Any, *, note: str | None = None) -> str:
    lines = [
        "<b>Настройки бота</b>",
        (
            "TG bot: "
            + html.escape(
                (
                    f"@{snapshot.telegram_bot_username} ({snapshot.telegram_bot_id})"
                    if snapshot.telegram_bot_username and snapshot.telegram_bot_id is not None
                    else (
                        f"{snapshot.telegram_bot_display_name} ({snapshot.telegram_bot_id})"
                        if snapshot.telegram_bot_display_name and snapshot.telegram_bot_id is not None
                        else "-"
                    )
                )
            )
        ),
        f"ITS: <b>{html.escape(snapshot.its_runtime_status)}</b>",
        f"Session: {'есть' if snapshot.session_file_exists else 'нет'}",
        f"ITS bot: {html.escape(snapshot.its_bot_username or '-')}",
        f"ITS source: {html.escape(snapshot.its_bot_username_source or '-')}",
        f"TG creds: {'ok' if snapshot.tg_api_id_present and snapshot.tg_api_hash_present else 'missing'}",
        f"Worker: {'on' if snapshot.worker_running else 'off'} | inflight={snapshot.inflight_count} | queue={snapshot.queue_size}",
        f"Price topic: {snapshot.price_topic_id if snapshot.price_topic_id is not None else '-'}",
        f"Settings topic: {snapshot.settings_topic_id if snapshot.settings_topic_id is not None else '-'}",
        f"Chat: {snapshot.target_chat_id}",
        f"Session path: {html.escape(snapshot.its_session_path or '-')}",
    ]
    if snapshot.session_file_mtime:
        lines.append(f"Session mtime: {html.escape(snapshot.session_file_mtime)}")
    if snapshot.startup_error:
        lines.append(f"Последняя ошибка: {html.escape(snapshot.startup_error)}")
    if note:
        lines.append("")
        lines.append(f"<b>Статус:</b> {html.escape(note)}")
    return "\n".join(lines)


def _format_topics_card(runtime_settings: TgBotRuntimeSettings, *, note: str | None = None) -> str:
    lines = [
        "<b>Темы Telegram runtime</b>",
        f"Chat: {runtime_settings.target_chat_id or '-'}",
        f"Allowed: {', '.join(str(item) for item in runtime_settings.allowed_topic_ids) or '-'}",
        "Comments:",
        html.escape(_format_request_comment_map(runtime_settings.request_comment_topic_map)),
        f"Price: {runtime_settings.price_topic_id if runtime_settings.price_topic_id is not None else '-'}",
        f"Settings: {runtime_settings.settings_topic_id if runtime_settings.settings_topic_id is not None else '-'}",
        "Suppliers:",
        html.escape(_format_supplier_topic_map(runtime_settings.supplier_topic_map)),
        "",
        "Изменения пишутся в TG runtime settings и применяются сразу.",
    ]
    if note:
        lines.append("")
        lines.append(f"<b>Статус:</b> {html.escape(note)}")
    return "\n".join(lines)


def _topic_prompt(field: str, runtime_settings: TgBotRuntimeSettings) -> str:
    if field == "target_chat_id":
        return _with_cancel_hint(
            f"Текущее значение {TOPIC_FIELD_LABELS[field]}: {runtime_settings.target_chat_id}\n"
            "Отправь новый chat id одним сообщением."
        )
    if field == "allowed_topic_ids":
        return _with_cancel_hint(
            f"Текущее значение {TOPIC_FIELD_LABELS[field]}: "
            f"{', '.join(str(item) for item in runtime_settings.allowed_topic_ids) or '-'}\n"
            "Отправь новый список через запятую, например: 1,2,3"
        )
    if field == "request_comment_topic_map":
        current = ",".join(
            f"{request}({comment})" for request, comment in sorted(runtime_settings.request_comment_topic_map.items())
        ) or "-"
        return _with_cancel_hint(
            f"Текущее значение {TOPIC_FIELD_LABELS[field]}: {current}\n"
            "Отправь новое значение в формате 45(35),23(59) или '-' чтобы очистить."
        )
    if field == "price_topic_id":
        return _with_cancel_hint(
            f"Текущее значение {TOPIC_FIELD_LABELS[field]}: "
            f"{runtime_settings.price_topic_id if runtime_settings.price_topic_id is not None else '-'}\n"
            "Отправь новый topic id или '-' чтобы очистить."
        )
    if field == "settings_topic_id":
        return _with_cancel_hint(
            f"Текущее значение {TOPIC_FIELD_LABELS[field]}: "
            f"{runtime_settings.settings_topic_id if runtime_settings.settings_topic_id is not None else '-'}\n"
            "Отправь новый topic id или '-' чтобы очистить."
        )
    if field == "supplier_topic_map":
        current = ",".join(
            f"{supplier}({topic})" for supplier, topic in sorted(runtime_settings.supplier_topic_map.items())
        ) or "-"
        return _with_cancel_hint(
            f"Текущее значение {TOPIC_FIELD_LABELS[field]}: {current}\n"
            "Отправь новое значение в формате Лена(4),Ветер(2) или '-' чтобы очистить."
        )
    raise ValueError(f"Неизвестное поле настроек тем: {field}")


class TgBotSettingsController:
    def __init__(
        self,
        *,
        settings: AppSettings,
        settings_service: TgBotSettingsService,
        bot_client: TelegramBotClient,
        its_service: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._settings_service = settings_service
        self._bot_client = bot_client
        self._its_service = its_service
        self._logger = logger or logging.getLogger("agent_ui.interfaces.tg_bot.settings")
        self._pending_topic_edits: dict[tuple[int, int], PendingTopicEdit] = {}
        self._pending_logins: dict[tuple[int, int], PendingSessionLogin] = {}
        self._active_login_owner_by_chat: dict[int, int] = {}

    def _runtime_settings(self) -> TgBotRuntimeSettings:
        return self._settings_service.load()

    def _is_settings_topic(self, *, chat_id: int, topic_id: int | None) -> bool:
        runtime_settings = self._runtime_settings()
        target_chat_ok = runtime_settings.target_chat_id == 0 or chat_id == runtime_settings.target_chat_id
        return bool(
            target_chat_ok
            and runtime_settings.settings_topic_id is not None
            and topic_id == runtime_settings.settings_topic_id
        )

    def _is_admin(self, user_id: int | None) -> bool:
        return is_settings_admin(runtime_settings=self._runtime_settings(), user_id=user_id)

    async def _safe_answer_callback(self, query: CallbackQuery, text: str, *, show_alert: bool = False) -> None:
        try:
            await query.answer(text, show_alert=show_alert)
        except TelegramBadRequest:
            self._logger.info("Skip expired settings callback data=%s", getattr(query, "data", None))

    async def _send_message(
        self,
        *,
        chat_id: int,
        topic_id: int | None,
        text: str,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Any:
        return await self._bot_client.send_message(
            chat_id=chat_id,
            message_thread_id=topic_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=True if parse_mode == "HTML" else None,
            reply_markup=reply_markup,
        )

    async def _edit_or_send(self, *, query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None) -> None:
        callback_message = getattr(query, "message", None)
        if callback_message is None:
            return
        try:
            await self._bot_client.edit_message_text(
                chat_id=callback_message.chat.id,
                message_id=callback_message.message_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        except Exception:
            self._logger.info("Fallback to send_message for settings callback data=%s", getattr(query, "data", None))
            await self._send_message(
                chat_id=callback_message.chat.id,
                topic_id=getattr(callback_message, "message_thread_id", None),
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

    async def _send_status_card(
        self,
        *,
        chat_id: int,
        topic_id: int | None,
        reply_to_message_id: int | None = None,
        note: str | None = None,
    ) -> Any:
        snapshot = await build_settings_status_snapshot(
            settings=self._settings,
            settings_service=self._settings_service,
            its_service=self._its_service,
            bot_client=self._bot_client,
        )
        return await self._send_message(
            chat_id=chat_id,
            topic_id=topic_id,
            reply_to_message_id=reply_to_message_id,
            text=_format_status_card(snapshot, note=note),
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )

    async def _send_topics_card(
        self,
        *,
        chat_id: int,
        topic_id: int | None,
        reply_to_message_id: int | None = None,
        note: str | None = None,
    ) -> Any:
        runtime_settings = self._runtime_settings()
        return await self._send_message(
            chat_id=chat_id,
            topic_id=topic_id,
            reply_to_message_id=reply_to_message_id,
            text=_format_topics_card(runtime_settings, note=note),
            parse_mode="HTML",
            reply_markup=_topics_keyboard(),
        )

    async def handle_message(self, *, message: Message, message_text: str | None) -> bool:
        chat_id = message.chat.id
        topic_id = message.message_thread_id
        if not self._is_settings_topic(chat_id=chat_id, topic_id=topic_id):
            return False
        user_id = message.from_user.id if getattr(message, "from_user", None) is not None else None
        if not self._is_admin(user_id):
            await self._send_message(
                chat_id=chat_id,
                topic_id=topic_id,
                reply_to_message_id=message.message_id,
                text="Нет доступа к настройкам бота.",
            )
            return True

        text = (message_text or "").strip()
        state_key = (chat_id, int(user_id or 0))
        if _is_bot_command(text, "/cancel"):
            await self._cancel_state(state_key=state_key)
            await self._send_message(
                chat_id=chat_id,
                topic_id=topic_id,
                reply_to_message_id=message.message_id,
                text="Действие отменено.",
            )
            return True
        if state_key in self._pending_logins:
            await self._handle_login_input(message=message, text=text, state_key=state_key)
            return True
        if state_key in self._pending_topic_edits:
            await self._handle_topic_edit_input(message=message, text=text, state_key=state_key)
            return True
        if _is_bot_command(text, "/bot"):
            await self._send_status_card(
                chat_id=chat_id,
                topic_id=topic_id,
                reply_to_message_id=message.message_id,
            )
            return True
        await self._send_message(
            chat_id=chat_id,
            topic_id=topic_id,
            reply_to_message_id=message.message_id,
            text="Используй /bot. Если идёт мастер ввода, можно написать /cancel.",
        )
        return True

    async def handle_callback(self, *, query: CallbackQuery) -> bool:
        data = getattr(query, "data", "") or ""
        if not data.startswith(SETTINGS_CALLBACK_PREFIX):
            return False
        callback_message = getattr(query, "message", None)
        if callback_message is None:
            await self._safe_answer_callback(query, "Сообщение недоступно.", show_alert=True)
            return True

        chat_id = callback_message.chat.id
        topic_id = getattr(callback_message, "message_thread_id", None)
        user_id = query.from_user.id if getattr(query, "from_user", None) is not None else None
        if not self._is_settings_topic(chat_id=chat_id, topic_id=topic_id):
            await self._safe_answer_callback(query, "Это не тема настроек.", show_alert=True)
            return True
        if not self._is_admin(user_id):
            await self._safe_answer_callback(query, "Нет доступа к настройкам.", show_alert=True)
            return True

        state_key = (chat_id, int(user_id or 0))
        if data in {CALLBACK_MAIN, CALLBACK_REFRESH, CALLBACK_TOPICS_BACK}:
            snapshot = await build_settings_status_snapshot(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
                bot_client=self._bot_client,
            )
            await self._edit_or_send(query=query, text=_format_status_card(snapshot), reply_markup=_main_keyboard())
            await self._safe_answer_callback(query, "Статус обновлен.")
            return True
        if data == CALLBACK_CHECK_ACCESS:
            result = await perform_its_access_check(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
            )
            snapshot = await build_settings_status_snapshot(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
                bot_client=self._bot_client,
            )
            await self._edit_or_send(
                query=query,
                text=_format_status_card(snapshot, note=result.message),
                reply_markup=_main_keyboard(),
            )
            await self._safe_answer_callback(query, "Проверка доступа завершена.")
            return True
        if data == CALLBACK_DELETE_SESSION:
            await self._edit_or_send(
                query=query,
                text="Удалить текущую ITS-session? Файлы будут перемещены в quarantine.",
                reply_markup=_delete_confirm_keyboard(),
            )
            await self._safe_answer_callback(query, "Нужно подтверждение.")
            return True
        if data == CALLBACK_DELETE_CANCEL:
            snapshot = await build_settings_status_snapshot(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
                bot_client=self._bot_client,
            )
            await self._edit_or_send(query=query, text=_format_status_card(snapshot), reply_markup=_main_keyboard())
            await self._safe_answer_callback(query, "Удаление отменено.")
            return True
        if data == CALLBACK_DELETE_CONFIRM:
            if chat_id in self._active_login_owner_by_chat:
                await self._safe_answer_callback(query, "Сначала завершите активный login wizard.", show_alert=True)
                return True
            result = await delete_current_session(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
            )
            snapshot = await build_settings_status_snapshot(
                settings=self._settings,
                settings_service=self._settings_service,
                its_service=self._its_service,
                bot_client=self._bot_client,
            )
            note = (
                f"Session удалена. Перемещено файлов: {len(result.moved_paths)}"
                if result.moved_paths
                else "Session-файлы не найдены, runtime обновлен."
            )
            await self._edit_or_send(
                query=query,
                text=_format_status_card(snapshot, note=note),
                reply_markup=_main_keyboard(),
            )
            await self._safe_answer_callback(query, "Session удалена.")
            return True
        if data == CALLBACK_ADD_SESSION:
            if chat_id in self._active_login_owner_by_chat and self._active_login_owner_by_chat[chat_id] != int(user_id or 0):
                await self._safe_answer_callback(query, "Login wizard уже запущен другим админом.", show_alert=True)
                return True
            production_session_path = resolve_session_path(
                settings=self._settings,
                settings_service=self._settings_service,
                its_config=(getattr(self._its_service, "config", None) if self._its_service is not None else None),
            )
            if related_session_files(production_session_path):
                await self._safe_answer_callback(
                    query,
                    "Сначала удалите текущую session через кнопку 'Удалить сессию'.",
                    show_alert=True,
                )
                return True
            api_id = _env("TG_API_ID")
            api_hash = _env("TG_API_HASH")
            if not (api_id and api_hash):
                await self._safe_answer_callback(query, "В env не хватает TG_API_ID / TG_API_HASH.", show_alert=True)
                return True
            temp_session_path = production_session_path.with_name(
                f"{production_session_path.stem}.pending_{chat_id}_{int(user_id or 0)}.session"
            )
            login = InteractiveSessionLogin(api_id=api_id, api_hash=api_hash, session_path=temp_session_path)
            self._pending_logins[state_key] = PendingSessionLogin(login=login, step="phone")
            self._active_login_owner_by_chat[chat_id] = int(user_id or 0)
            await self._send_message(
                chat_id=chat_id,
                topic_id=topic_id,
                text="Введите номер телефона для новой Telegram session. Для отмены: /cancel",
            )
            await self._safe_answer_callback(query, "Ожидаю номер телефона.")
            return True
        if data == CALLBACK_TOPICS:
            await self._edit_or_send(
                query=query,
                text=_format_topics_card(self._runtime_settings()),
                reply_markup=_topics_keyboard(),
            )
            await self._safe_answer_callback(query, "Открыты настройки тем.")
            return True
        if data.startswith(CALLBACK_TOPIC_EDIT_PREFIX):
            token = data.split(":", maxsplit=2)[-1]
            field = TOPIC_EDIT_TOKEN_MAP.get(token)
            if field is None:
                await self._safe_answer_callback(query, "Неизвестное поле тем.", show_alert=True)
                return True
            self._pending_topic_edits[state_key] = PendingTopicEdit(field=field)
            await self._send_message(
                chat_id=chat_id,
                topic_id=topic_id,
                text=_topic_prompt(field, self._runtime_settings()),
            )
            await self._safe_answer_callback(query, f"Ожидаю новое значение {TOPIC_FIELD_LABELS[field]}.")
            return True
        await self._safe_answer_callback(query, "Неизвестная команда settings.", show_alert=True)
        return True

    async def _cancel_state(self, *, state_key: tuple[int, int]) -> None:
        pending_login = self._pending_logins.pop(state_key, None)
        if pending_login is not None:
            self._active_login_owner_by_chat.pop(state_key[0], None)
            await pending_login.login.close()
            cleanup_temp_session_files(pending_login.login.session_path)
        self._pending_topic_edits.pop(state_key, None)

    async def _handle_login_input(self, *, message: Message, text: str, state_key: tuple[int, int]) -> None:
        pending = self._pending_logins.get(state_key)
        if pending is None:
            return
        topic_id = message.message_thread_id
        if pending.step == "phone":
            progress = await pending.login.start(text)
            if progress.status == "code_sent":
                pending.step = "code"
            await self._send_message(
                chat_id=message.chat.id,
                topic_id=topic_id,
                reply_to_message_id=message.message_id,
                text=progress.message,
            )
            await self._delete_sensitive_message(message)
            return
        if pending.step == "code":
            progress = await pending.login.submit_code(text)
            if progress.status == "need_password":
                pending.step = "password"
                await self._send_message(
                    chat_id=message.chat.id,
                    topic_id=topic_id,
                    reply_to_message_id=message.message_id,
                    text=progress.message,
                )
                await self._delete_sensitive_message(message)
                return
            if progress.status == "done":
                temp_session_path = pending.login.session_path
                await pending.login.close()
                install_result = await install_temp_session(
                    settings=self._settings,
                    settings_service=self._settings_service,
                    temp_session_path=temp_session_path,
                    its_service=self._its_service,
                )
                self._pending_logins.pop(state_key, None)
                self._active_login_owner_by_chat.pop(message.chat.id, None)
                await self._delete_sensitive_message(message)
                await self._send_status_card(
                    chat_id=message.chat.id,
                    topic_id=topic_id,
                    reply_to_message_id=message.message_id,
                    note=f"Новая session активна. Файлов установлено: {len(install_result.installed_paths)}",
                )
                return
            await self._send_message(
                chat_id=message.chat.id,
                topic_id=topic_id,
                reply_to_message_id=message.message_id,
                text=progress.message,
            )
            await self._delete_sensitive_message(message)
            return
        if pending.step == "password":
            progress = await pending.login.submit_password(text)
            if progress.status == "done":
                temp_session_path = pending.login.session_path
                await pending.login.close()
                install_result = await install_temp_session(
                    settings=self._settings,
                    settings_service=self._settings_service,
                    temp_session_path=temp_session_path,
                    its_service=self._its_service,
                )
                self._pending_logins.pop(state_key, None)
                self._active_login_owner_by_chat.pop(message.chat.id, None)
                await self._delete_sensitive_message(message)
                await self._send_status_card(
                    chat_id=message.chat.id,
                    topic_id=topic_id,
                    reply_to_message_id=message.message_id,
                    note=f"Новая session активна. Файлов установлено: {len(install_result.installed_paths)}",
                )
                return
            await self._send_message(
                chat_id=message.chat.id,
                topic_id=topic_id,
                reply_to_message_id=message.message_id,
                text=progress.message,
            )
            await self._delete_sensitive_message(message)

    async def _handle_topic_edit_input(self, *, message: Message, text: str, state_key: tuple[int, int]) -> None:
        pending = self._pending_topic_edits.get(state_key)
        if pending is None:
            return
        runtime_settings = self._runtime_settings()
        try:
            updated = apply_runtime_settings_update(
                runtime_settings=runtime_settings,
                field=pending.field,
                raw_value=text,
            )
        except Exception as exc:
            await self._send_message(
                chat_id=message.chat.id,
                topic_id=message.message_thread_id,
                reply_to_message_id=message.message_id,
                text=f"Не удалось сохранить {TOPIC_FIELD_LABELS[pending.field]}: {exc}",
            )
            return
        await self._settings_service.save_async(updated)
        self._pending_topic_edits.pop(state_key, None)
        await self._send_topics_card(
            chat_id=message.chat.id,
            topic_id=message.message_thread_id,
            reply_to_message_id=message.message_id,
            note=f"{TOPIC_FIELD_LABELS[pending.field]} обновлен и сохранен в TG runtime settings.",
        )

    async def _delete_sensitive_message(self, message: Message) -> None:
        try:
            await self._bot_client.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            self._logger.info("Failed to delete sensitive settings message_id=%s", message.message_id)


__all__ = [
    "CALLBACK_ADD_SESSION",
    "CALLBACK_CHECK_ACCESS",
    "CALLBACK_DELETE_CANCEL",
    "CALLBACK_DELETE_CONFIRM",
    "CALLBACK_DELETE_SESSION",
    "CALLBACK_MAIN",
    "CALLBACK_REFRESH",
    "CALLBACK_TOPIC_EDIT_PREFIX",
    "CALLBACK_TOPICS",
    "CALLBACK_TOPICS_BACK",
    "PendingSessionLogin",
    "PendingTopicEdit",
    "TgBotSettingsController",
]
