import { getJson, postForm, postFormWithProgress, postJson } from "./api.js";
import {
  renderAnalysis,
  renderBatchStatus,
  renderCarousel,
  renderCaseMeta,
  renderCaseProgressOverlay,
  renderChat,
  renderCounters,
  renderImages,
  renderModule0Status,
  renderQuestions,
  renderRootSelect,
  renderOutputStatusLine,
  renderSourceTable,
  renderSummary,
} from "./render.js";
import { appState } from "./state.js";

const dom = {
  rootSelect: document.getElementById("root-select"),
  refreshWorkspaceButton: document.getElementById("refresh-workspace-button"),
  deleteRootButton: document.getElementById("delete-root-button"),
  toggleHelperButton: document.getElementById("toggle-helper-button"),
  openWorkbookRulesButton: document.getElementById("open-workbook-rules-button"),
  toolbarHelper: document.getElementById("toolbar-helper"),
  toolbarHelperRates: document.getElementById("toolbar-helper-rates"),
  batchStatusBanner: document.getElementById("batch-status-banner"),
  runOcrButton: document.getElementById("run-ocr-button"),
  prefetchButton: document.getElementById("prefetch-button"),
  stopOcrButton: document.getElementById("stop-ocr-button"),
  saveExcelButton: document.getElementById("save-excel-button"),
  skipCaseButton: document.getElementById("skip-case-button"),
  metricTotal: document.getElementById("metric-total"),
  metricSaved: document.getElementById("metric-saved"),
  metricSkipped: document.getElementById("metric-skipped"),
  openItsSettingsButton: document.getElementById("open-its-settings-button"),
  rowCarousel: document.getElementById("row-carousel"),
  tabWorkspaceButton: document.getElementById("tab-workspace-button"),
  tabTableButton: document.getElementById("tab-table-button"),
  workspaceView: document.getElementById("workspace-view"),
  caseProgressOverlay: document.getElementById("case-progress-overlay"),
  tableView: document.getElementById("table-view"),
  imageGrid: document.getElementById("image-grid"),
  caseCaption: document.getElementById("case-caption"),
  backgroundBadge: document.getElementById("background-badge"),
  analysisContent: document.getElementById("analysis-content"),
  workStage: document.getElementById("work-stage"),
  chatMessages: document.getElementById("chat-messages"),
  modelQuestions: document.getElementById("model-questions"),
  focusChatButton: document.getElementById("focus-chat-button"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  chatSubmitButton: document.querySelector("#chat-form button[type='submit']"),
  outputCanvas: document.getElementById("output-canvas"),
  outputStatusLine: document.getElementById("output-status-line"),
  sourceTableWrap: document.getElementById("source-table-wrap"),
  toggleWorkbookButton: document.getElementById("toggle-workbook-button"),
  workbookDrawer: document.getElementById("workbook-drawer"),
  workbookFile: document.getElementById("workbook-file"),
  workbookFileName: document.getElementById("workbook-file-name"),
  sheetSelect: document.getElementById("sheet-select"),
  rowsInput: document.getElementById("rows-input"),
  workbookAutoExtra: document.getElementById("workbook-auto-extra"),
  workbookSkipAutorun: document.getElementById("workbook-skip-autorun"),
  detectDuplicates: document.getElementById("detect-duplicates"),
  runWorkbookButton: document.getElementById("run-workbook-button"),
  workbookStatus: document.getElementById("workbook-status"),
  workbookOverlay: document.getElementById("workbook-overlay"),
  workbookOverlayTitle: document.getElementById("workbook-overlay-title"),
  workbookOverlayText: document.getElementById("workbook-overlay-text"),
  workbookOverlayExtra: document.getElementById("workbook-overlay-extra"),
  workbookOverlaySkip: document.getElementById("workbook-overlay-skip"),
  workbookRulesModal: document.getElementById("workbook-rules-modal"),
  workbookRulesTitle: document.getElementById("workbook-rules-title"),
  workbookRulesSummary: document.getElementById("workbook-rules-summary"),
  workbookRulesErrors: document.getElementById("workbook-rules-errors"),
  workbookRulesMeta: document.getElementById("workbook-rules-meta"),
  closeWorkbookRulesButton: document.getElementById("close-workbook-rules-button"),
  ackWorkbookRulesButton: document.getElementById("ack-workbook-rules-button"),
  itsSettingsModal: document.getElementById("its-settings-modal"),
  closeItsSettingsButton: document.getElementById("close-its-settings-button"),
  itsRuntimeStatus: document.getElementById("its-runtime-status"),
  itsBotUsername: document.getElementById("its-bot-username"),
  itsSessionFileStatus: document.getElementById("its-session-file-status"),
  itsApiStatus: document.getElementById("its-api-status"),
  itsWorkerStatus: document.getElementById("its-worker-status"),
  itsSessionPath: document.getElementById("its-session-path"),
  itsStatusNote: document.getElementById("its-status-note"),
  itsStartupError: document.getElementById("its-startup-error"),
  itsEnabledStatus: document.getElementById("its-enabled-status"),
  itsEnabledToggleButton: document.getElementById("its-enabled-toggle-button"),
  itsRefreshButton: document.getElementById("its-refresh-button"),
  itsCheckAccessButton: document.getElementById("its-check-access-button"),
  itsTestQueryButton: document.getElementById("its-test-query-button"),
  itsCancelLoginButton: document.getElementById("its-cancel-login-button"),
  itsDeleteSessionButton: document.getElementById("its-delete-session-button"),
  itsPendingStepBadge: document.getElementById("its-pending-step-badge"),
  itsPhoneInput: document.getElementById("its-phone-input"),
  itsStartLoginButton: document.getElementById("its-start-login-button"),
  itsCodeRow: document.getElementById("its-code-row"),
  itsCodeInput: document.getElementById("its-code-input"),
  itsSubmitCodeButton: document.getElementById("its-submit-code-button"),
  itsPasswordRow: document.getElementById("its-password-row"),
  itsPasswordInput: document.getElementById("its-password-input"),
  itsSubmitPasswordButton: document.getElementById("its-submit-password-button"),
  itsTestCodeInput: document.getElementById("its-test-code-input"),
  itsAccessResult: document.getElementById("its-access-result"),
  itsTestSummary: document.getElementById("its-test-summary"),
  itsTestParsed: document.getElementById("its-test-parsed"),
  itsTestRaw: document.getElementById("its-test-raw"),
  imageModal: document.getElementById("image-modal"),
  imageModalContent: document.getElementById("image-modal-content"),
  closeImageModalButton: document.getElementById("close-image-modal-button"),
  ecoDbEntryModal: document.getElementById("eco-db-entry-modal"),
  ecoDbEntryContent: document.getElementById("eco-db-entry-content"),
  closeEcoDbEntryModalButton: document.getElementById("close-eco-db-entry-modal-button"),
};

let pollInFlight = false;
let lastWorkspaceSignature = "";
let lastJobsSignature = "";
const chatHistoryPromises = new Map();
const BATCH_SIZE = 5;
let activeOcrAbortController = null;
let authGateElement = null;

function escapeInlineHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildSignature(value) {
  try {
    return JSON.stringify(value ?? null);
  } catch {
    return `${Date.now()}`;
  }
}

async function ensureAuthenticated() {
  const status = await getJson("/api/auth/status");
  if (!status.enabled || status.authenticated) {
    return;
  }
  await showAuthGate();
}

function showAuthGate() {
  return new Promise((resolve) => {
    authGateElement?.remove();
    const gate = document.createElement("section");
    gate.className = "auth-gate";
    gate.innerHTML = `
      <form class="auth-gate-card">
        <div class="auth-gate-kicker">Доступ к серверу</div>
        <h1>Введите пароль</h1>
        <p>После входа браузер запомнит доступ на этом устройстве. Таблицы и состояние останутся общими на VPS.</p>
        <label class="auth-gate-field">
          <span>Пароль</span>
          <input class="auth-gate-input" type="password" autocomplete="current-password" autofocus />
        </label>
        <div class="auth-gate-error" aria-live="polite"></div>
        <button class="primary-button auth-gate-submit" type="submit">Войти</button>
      </form>
    `;
    document.body.appendChild(gate);
    document.body.classList.add("is-auth-locked");
    authGateElement = gate;

    const form = gate.querySelector("form");
    const input = gate.querySelector("input");
    const button = gate.querySelector("button");
    const errorBox = gate.querySelector(".auth-gate-error");
    window.setTimeout(() => input?.focus(), 50);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const password = input.value;
      errorBox.textContent = "";
      button.disabled = true;
      try {
        const payload = await postJson("/api/auth/login", { password });
        if (!payload?.authenticated) {
          throw new Error("Пароль не подошел.");
        }
        gate.remove();
        document.body.classList.remove("is-auth-locked");
        authGateElement = null;
        resolve();
      } catch (_error) {
        errorBox.textContent = "Пароль не подошел. Проверьте ввод и попробуйте еще раз.";
        input.select();
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderToolbarHelper() {
  const rates = appState.currencyRates || null;
  const badges = [];
  if (rates?.usd && Number.isFinite(Number(rates.usd.value_rub))) {
    badges.push(`USD ${Number(rates.usd.value_rub).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} ₽`);
  }
  if (rates?.eur && Number.isFinite(Number(rates.eur.value_rub))) {
    badges.push(`EUR ${Number(rates.eur.value_rub).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} ₽`);
  }
  if (!dom.toolbarHelperRates) {
    return;
  }
  dom.toolbarHelperRates.innerHTML = `
    ${
      badges.length
        ? `<div class="toolbar-helper-chip is-currency"><strong>Курсы ЦБ</strong> ${escapeInlineHtml(badges.join(" · "))}${rates?.date ? ` · ${escapeInlineHtml(rates.date)}` : ""}</div>`
        : ""
    }
    ${
      rates?.note
        ? `<div class="toolbar-helper-chip is-currency-note">${escapeInlineHtml(rates.note)}</div>`
        : ""
    }
  `;
}

function getCurrentCase() {
  return appState.workspace?.current_case || null;
}

function getCurrentCaseId() {
  return getCurrentCase()?.case_id || "";
}

function setItsSessionStatus(payload) {
  appState.itsSessionStatus = payload || null;
  if (!appState.itsForm.testCode && payload?.suggested_test_code) {
    appState.itsForm.testCode = payload.suggested_test_code;
  }
}

function applyItsDiagnostic(payload) {
  setItsSessionStatus(payload?.status || null);
  appState.itsAccessCheck = payload?.access_check || null;
  appState.itsTestQuery = payload?.test_query || null;
}

async function refreshItsSessionStatus({ silent = false } = {}) {
  try {
    const payload = await getJson("/api/its-session/status/");
    setItsSessionStatus(payload);
    renderWorkspace();
    return payload;
  } catch (error) {
    if (!silent) {
      showError(error);
    }
    throw error;
  }
}

function closeItsSettingsModal() {
  appState.isItsModalOpen = false;
  renderWorkspace();
}

async function openItsSettingsModal() {
  appState.isItsModalOpen = true;
  renderWorkspace();
  await refreshItsSessionStatus({ silent: false });
}

function formatItsParsedReply(testQuery) {
  if (!testQuery?.parsed_reply) {
    return "—";
  }
  return JSON.stringify(testQuery.parsed_reply, null, 2);
}

function formatItsSummary(testQuery) {
  if (!testQuery) {
    return "Нажми «Тест ITS», чтобы отправить код в live-бот.";
  }
  const parts = [
    `status=${testQuery.status || "—"}`,
    `code=${testQuery.code || "—"}`,
    testQuery.reply_variant !== null && testQuery.reply_variant !== undefined ? `variant=${testQuery.reply_variant}` : "",
    testQuery.its_value !== null && testQuery.its_value !== undefined ? `its=${testQuery.its_value}` : "",
    testQuery.its_bracket_value !== null && testQuery.its_bracket_value !== undefined ? `its_scob=${testQuery.its_bracket_value}` : "",
    testQuery.date_text ? `date=${testQuery.date_text}` : "",
    testQuery.reply_code_match_status ? `match=${testQuery.reply_code_match_status}` : "",
  ].filter(Boolean);
  return parts.join(" | ");
}

function renderItsSessionModal() {
  const isOpen = Boolean(appState.isItsModalOpen);
  const status = appState.itsSessionStatus || null;
  const accessCheck = appState.itsAccessCheck || null;
  const testQuery = appState.itsTestQuery || null;
  const pendingStep = status?.pending_step || "";

  dom.itsSettingsModal.classList.toggle("is-hidden", !isOpen);
  dom.openItsSettingsButton?.classList.toggle("is-active", isOpen);

  if (!status) {
    dom.itsRuntimeStatus.textContent = "—";
    dom.itsBotUsername.textContent = "—";
    dom.itsSessionFileStatus.textContent = "—";
    dom.itsApiStatus.textContent = "—";
    dom.itsWorkerStatus.textContent = "—";
    dom.itsSessionPath.textContent = "—";
    dom.itsStatusNote.textContent = "Открой окно и проверь доступ перед первым запуском.";
    dom.itsStartupError.classList.add("is-hidden");
    dom.itsStartupError.textContent = "";
    dom.itsPendingStepBadge.textContent = "idle";
    dom.itsEnabledStatus.textContent = "Статус пока не загружен.";
    dom.itsEnabledToggleButton.textContent = "Переключить ITS";
  } else {
    dom.itsRuntimeStatus.textContent = status.runtime_status || "—";
    dom.itsBotUsername.textContent = status.its_bot_username || "—";
    dom.itsSessionFileStatus.textContent = status.session_file_exists ? "есть" : "нет";
    dom.itsApiStatus.textContent = status.tg_api_ready ? "ok" : "missing";
    dom.itsWorkerStatus.textContent = status.worker_running ? "running" : "idle";
    dom.itsSessionPath.textContent = status.its_session_path || "—";
    dom.itsStatusNote.textContent = status.note || "Проверь runtime status, затем Telegram access и тестовый ITS-запрос.";
    const startupError = String(status.startup_error || "").trim();
    dom.itsStartupError.classList.toggle("is-hidden", !startupError);
    dom.itsStartupError.textContent = startupError ? `Startup error: ${startupError}` : "";
    dom.itsPendingStepBadge.textContent = pendingStep || "idle";
    if (status.its_enabled) {
      dom.itsEnabledStatus.textContent = "Включен: подбор кодов будет пробовать получить ITS из Telegram-бота.";
      dom.itsEnabledToggleButton.textContent = "Выключить ITS";
    } else {
      dom.itsEnabledStatus.textContent = "Выключен: если бот лежит, подбор продолжит работу без ожидания Telegram.";
      dom.itsEnabledToggleButton.textContent = "Включить ITS";
    }
  }

  dom.itsPhoneInput.value = appState.itsForm.phone;
  dom.itsCodeInput.value = appState.itsForm.code;
  dom.itsPasswordInput.value = appState.itsForm.password;
  dom.itsTestCodeInput.value = appState.itsForm.testCode;

  dom.itsCodeRow.classList.toggle("is-hidden", pendingStep !== "code");
  dom.itsPasswordRow.classList.toggle("is-hidden", pendingStep !== "password");

  if (accessCheck) {
    dom.itsAccessResult.innerHTML = `
      <strong>${escapeInlineHtml(accessCheck.ok ? "Доступ подтвержден" : "Доступ не подтвержден")}</strong><br />
      status=${escapeInlineHtml(accessCheck.status || "—")}<br />
      ${escapeInlineHtml(accessCheck.message || "—")}
    `;
  } else {
    dom.itsAccessResult.textContent = "Нажми «Проверить доступ к ТГ».";
  }

  dom.itsTestSummary.textContent = formatItsSummary(testQuery);
  dom.itsTestParsed.textContent = formatItsParsedReply(testQuery);
  dom.itsTestRaw.textContent = testQuery?.raw_reply || "—";
}

function currentCaseHasAiResult(currentCase) {
  if (!currentCase) {
    return false;
  }
  return Boolean(currentCase.has_ai_result);
}

function currentCaseHasActiveGeneration(currentCase) {
  if (!currentCase) {
    return false;
  }
  const status = String(currentCase.ocr_status || "").toLowerCase();
  const prefetchStatus = String(currentCase.prefetch_status || currentCase.background_status || "").toLowerCase();
  return ["running", "queued", "cancelling"].includes(status) || ["running", "queued", "cancelling"].includes(prefetchStatus);
}

function updateWorkbookFileName() {
  if (!dom.workbookFileName) {
    return;
  }
  const file = dom.workbookFile?.files?.[0];
  dom.workbookFileName.textContent = file?.name || "Файл еще не выбран";
}

function resetWorkbookFileSelection() {
  if (!dom.workbookFile) {
    return;
  }
  dom.workbookFile.value = "";
  updateWorkbookFileName();
}

function setWorkbookUploadProgress(progress) {
  appState.workbookUploadProgress = progress;
}

function clearWorkbookUploadProgress() {
  appState.isWorkbookUploading = false;
  appState.workbookUploadProgress = null;
}

function getWorkbookAutorunCount() {
  return BATCH_SIZE + (appState.workbookAutoRunExtraRows ? 10 : 0);
}

function setWorkbookOverlay(overlay) {
  appState.workbookOverlay = overlay;
}

function clearWorkbookOverlay() {
  appState.workbookOverlay = null;
}

function openWorkbookRulesModal(inspectPayload = null) {
  appState.workbookRulesModal = { inspectPayload };
}

function closeWorkbookRulesModal() {
  appState.workbookRulesModal = null;
}

function buildWorkbookRulesMeta(inspectPayload) {
  if (!inspectPayload) {
    return "";
  }
  const matched = inspectPayload.matched_required_headers || {};
  const mergedRanges = Array.isArray(inspectPayload.merged_ranges) ? inspectPayload.merged_ranges : [];
  return [
    `<div><strong>Лист:</strong> ${escapeInlineHtml(inspectPayload.selected_sheet || "—")}</div>`,
    `<div><strong>Строк с данными:</strong> ${escapeInlineHtml(String(inspectPayload.total_data_rows || 0))}</div>`,
    `<div><strong>Наименование:</strong> ${escapeInlineHtml(matched["Наименование"] || "не найден")}</div>`,
    `<div><strong>Доп информация:</strong> ${escapeInlineHtml(matched["Доп информация"] || "не найдено, но это допустимо")}</div>`,
    inspectPayload.has_merged_cells
      ? `<div><strong>Объединенные ячейки:</strong> ${escapeInlineHtml(mergedRanges.slice(0, 6).join(", ") || "есть")}</div>`
      : "",
  ]
    .filter(Boolean)
    .join("");
}

function renderWorkbookRulesModal() {
  const modal = appState.workbookRulesModal;
  dom.workbookRulesModal.classList.toggle("is-hidden", !modal);
  if (!modal) {
    dom.workbookRulesSummary.className = "workbook-rules-summary";
    dom.workbookRulesSummary.textContent = "";
    dom.workbookRulesErrors.innerHTML = "";
    dom.workbookRulesMeta.innerHTML = "";
    return;
  }

  const inspectPayload = modal.inspectPayload || {};
  const validationErrors = Array.isArray(inspectPayload.validation_errors) ? inspectPayload.validation_errors : [];
  const hasInspectPayload = Boolean(inspectPayload && Object.keys(inspectPayload).length);
  const isCompatible = Boolean(inspectPayload.is_workbook_compatible);

  if (!hasInspectPayload) {
    dom.workbookRulesTitle.textContent = "Инструкция к импорту таблицы";
    dom.workbookRulesSummary.className = "workbook-rules-summary";
    dom.workbookRulesSummary.textContent =
      "Сначала проверьте структуру Excel, затем выбирайте файл и только после этого создавайте товары.";
    dom.workbookRulesErrors.innerHTML =
      '<div class="workbook-rules-ok">Это памятка по правильной подготовке таблицы. После выбора файла здесь появится и живая проверка ошибок.</div>';
    dom.workbookRulesMeta.innerHTML = "";
    return;
  }

  dom.workbookRulesTitle.textContent = isCompatible ? "Таблица выглядит корректно" : "Таблица пока не готова к запуску";
  dom.workbookRulesSummary.className = `workbook-rules-summary ${isCompatible ? "is-ok" : "is-error"}`;
  dom.workbookRulesSummary.textContent = isCompatible
    ? "Можно создавать товары. Перед запуском только проверьте диапазон строк и убедитесь, что изображения действительно лежат строго внутри своих строк."
    : "Есть ошибки в структуре таблицы. Исправьте их в Excel и затем выберите файл заново.";
  dom.workbookRulesErrors.innerHTML = isCompatible
    ? `<div class="workbook-rules-ok">Обязательные правила сейчас соблюдены.</div>`
    : validationErrors.map((item) => `<div class="workbook-rules-error">${escapeInlineHtml(item)}</div>`).join("");
  dom.workbookRulesMeta.innerHTML = buildWorkbookRulesMeta(inspectPayload);
}

function getActiveBatchJob() {
  return appState.jobs.find((job) => {
    if (job?.module_id !== "batch_ocr") {
      return false;
    }
    return ["queued", "running", "cancelling"].includes(String(job.status || "").toLowerCase());
  }) || null;
}

function collectActiveOcrCaseIds() {
  const caseIds = new Set();
  if (appState.localSingleRunCaseId) {
    caseIds.add(appState.localSingleRunCaseId);
  }

  const currentCase = getCurrentCase();
  const currentStatus = String(currentCase?.ocr_status || "").toLowerCase();
  if (currentCase?.case_id && ["running", "queued"].includes(currentStatus)) {
    caseIds.add(currentCase.case_id);
  }

  const activeBatchJob = getActiveBatchJob();
  const batchCaseIds = Array.isArray(activeBatchJob?.payload?.case_ids) ? activeBatchJob.payload.case_ids : [];
  for (const caseId of batchCaseIds) {
    if (caseId) {
      caseIds.add(caseId);
    }
  }

  const workspaceCases = Array.isArray(appState.workspace?.cases) ? appState.workspace.cases : [];
  for (const item of workspaceCases) {
    const prefetchStatus = String(item?.prefetch_status || "").toLowerCase();
    if (item?.case_id && ["queued", "running", "cancelling"].includes(prefetchStatus)) {
      caseIds.add(item.case_id);
    }
  }

  return [...caseIds];
}

function patchWorkspaceCaseState(caseIds, patch = {}) {
  if (!appState.workspace || !caseIds.length) {
    return;
  }

  const targetIds = new Set(caseIds.filter(Boolean));
  if (!targetIds.size) {
    return;
  }

  if (Array.isArray(appState.workspace.cases)) {
    appState.workspace.cases = appState.workspace.cases.map((item) => {
      if (!targetIds.has(item?.case_id)) {
        return item;
      }
      return {
        ...item,
        ...(patch.ocr_status ? { ocr_status: patch.ocr_status } : {}),
        ...(patch.prefetch_status ? { prefetch_status: patch.prefetch_status } : {}),
      };
    });
  }

  if (targetIds.has(appState.workspace.current_case?.case_id)) {
    appState.workspace.current_case = {
      ...appState.workspace.current_case,
      ...(patch.ocr_status ? { ocr_status: patch.ocr_status } : {}),
      ...(patch.background_status ? { background_status: patch.background_status } : {}),
    };
  }
}

function getWorkspaceForRender() {
  if (!appState.workspace) {
    return null;
  }

  const forcedStoppedCaseIds = new Set(appState.forcedStoppedCaseIds || []);
  const cases = Array.isArray(appState.workspace.cases) ? appState.workspace.cases.map((item) => ({ ...item })) : [];
  const currentCase = appState.workspace.current_case ? { ...appState.workspace.current_case } : null;

  for (const item of cases) {
    if (item.case_id === appState.localSingleRunCaseId) {
      item.ocr_status = "running";
    }
    if (forcedStoppedCaseIds.has(item.case_id)) {
      if (["queued", "running", "cancelling"].includes(String(item.prefetch_status || "").toLowerCase())) {
        item.prefetch_status = "cancelled";
      }
      if (
        item.case_id === appState.localSingleRunCaseId ||
        ["queued", "running"].includes(String(item.ocr_status || "").toLowerCase())
      ) {
        item.ocr_status = "cancelled";
      }
    }
  }

  if (currentCase) {
    if (currentCase.case_id === appState.localSingleRunCaseId) {
      currentCase.ocr_status = "running";
      currentCase.background_status = "running";
    }
    if (forcedStoppedCaseIds.has(currentCase.case_id)) {
      if (
        currentCase.case_id === appState.localSingleRunCaseId ||
        ["queued", "running", "cancelling"].includes(String(currentCase.background_status || "").toLowerCase()) ||
        ["queued", "running"].includes(String(currentCase.ocr_status || "").toLowerCase())
      ) {
        currentCase.ocr_status = "cancelled";
        currentCase.background_status = "cancelled";
      }
    }
  }

  return {
    ...appState.workspace,
    cases,
    current_case: currentCase,
  };
}

function getJobsForRender() {
  const jobs = Array.isArray(appState.jobs) ? appState.jobs.map((job) => ({ ...job })) : [];
  if (!appState.hideBatchBanner) {
    return jobs;
  }
  return jobs.filter((job) => job.module_id !== "batch_ocr");
}

function hasActiveOcrActivity() {
  if (appState.hideBatchBanner && !appState.isStoppingOcr) {
    return Boolean(activeOcrAbortController || appState.localSingleRunCaseId);
  }

  if (activeOcrAbortController) {
    return true;
  }

  if (appState.localSingleRunCaseId) {
    return true;
  }

  const currentCase = getCurrentCase();
  const currentStatus = String(currentCase?.ocr_status || "").toLowerCase();
  if (["running", "queued"].includes(currentStatus)) {
    return true;
  }

  return appState.jobs.some((job) => {
    if (job?.module_id !== "batch_ocr") {
      return false;
    }
    return ["queued", "running", "cancelling"].includes(String(job.status || "").toLowerCase());
  });
}

function getBatchTargetCases() {
  const cases = Array.isArray(appState.workspace?.cases) ? appState.workspace.cases : [];
  if (!cases.length) {
    return [];
  }
  const currentCaseId = getCurrentCaseId();
  const currentIndex = cases.findIndex((item) => item.case_id === currentCaseId);
  if (currentIndex < 0) {
    return cases.slice(0, BATCH_SIZE);
  }
  return cases.slice(currentIndex, currentIndex + BATCH_SIZE);
}

function buildBatchScopeLabel(targetCases) {
  if (!targetCases.length) {
    return `${BATCH_SIZE} товаров`;
  }

  const rowNumbers = targetCases
    .map((item) => Number(item?.row_number || 0))
    .filter((item) => Number.isFinite(item) && item > 0);

  if (rowNumbers.length === targetCases.length) {
    const first = Math.min(...rowNumbers);
    const last = Math.max(...rowNumbers);
    return first === last ? `строка ${first}` : `строки ${first}-${last}`;
  }

  return targetCases.length === 1 ? "1 товар" : `${targetCases.length} товаров`;
}

function confirmCurrentGeneration() {
  const currentCase = getCurrentCase();
  if (currentCaseHasActiveGeneration(currentCase)) {
    return window.confirm("По текущему товару уже идет подбор. Запустить заново?");
  }
  if (!currentCaseHasAiResult(currentCase)) {
    return true;
  }
  return window.confirm("По текущему товару уже есть GPT-результат. Перезапустить подбор заново?");
}

function confirmBatchGeneration() {
  const targetCases = getBatchTargetCases();
  const scopeLabel = buildBatchScopeLabel(targetCases);
  const existingCount = targetCases.filter((item) => item?.has_ai_result).length;
  const activeCount = targetCases.filter((item) => {
    const status = String(item?.prefetch_status || item?.ocr_status || "").toLowerCase();
    return ["queued", "running", "cancelling"].includes(status);
  }).length;
  if (activeCount && !existingCount) {
    return window.confirm(`В пакете (${scopeLabel}) уже выполняется подбор у ${activeCount} из ${targetCases.length}. Запустить заново?`);
  }
  if (!existingCount) {
    return true;
  }
  return window.confirm(
    `В пакете (${scopeLabel}) уже есть GPT-результат у ${existingCount} из ${targetCases.length}. Перезапустить подбор заново?`
  );
}

function getCodeOptions(currentCase) {
  return Array.isArray(currentCase?.code_options) ? currentCase.code_options : [];
}

function getSelectedCodeOption(currentCase) {
  if (!currentCase) {
    return null;
  }

  const options = getCodeOptions(currentCase);
  if (!options.length) {
    return null;
  }

  const storedOptionKey = appState.selectedCodeByCase[currentCase.case_id];
  const selectedOption = options.find((item) => item.option_key === storedOptionKey) || options[0];
  appState.selectedCodeByCase[currentCase.case_id] = selectedOption.option_key;
  return selectedOption;
}

function getAlternativeOptions(currentCase, selectedOption) {
  return getCodeOptions(currentCase).filter((item) => item.option_key !== selectedOption?.option_key);
}

function getEcoPacketForCode(currentCase, code) {
  const ecoFee = currentCase?.eco_fee;
  const packets = Array.isArray(ecoFee?.by_code) ? ecoFee.by_code : [];
  return packets.find((item) => String(item?.code || "") === String(code || "")) || null;
}

function getSelectedEcoYear(currentCase, selectedOption, ecoPacket) {
  if (!currentCase || !selectedOption || !ecoPacket) {
    return 2026;
  }
  const key = `${currentCase.case_id}|${selectedOption.code}`;
  const supportedYears = Array.isArray(ecoPacket.supported_years) ? ecoPacket.supported_years : [];
  const storedYear = Number(
    appState.selectedEcoYearByCaseCode[key] || ecoPacket.selected_year || ecoPacket.default_year || 2026
  );
  const year = supportedYears.includes(storedYear)
    ? storedYear
    : Number(ecoPacket.selected_year || ecoPacket.default_year || supportedYears[0] || 2026);
  appState.selectedEcoYearByCaseCode[key] = year;
  return year;
}

function getEcoYearPayload(ecoPacket, year) {
  const rows = Array.isArray(ecoPacket?.years) ? ecoPacket.years : [];
  return rows.find((item) => Number(item?.year) === Number(year)) || null;
}

function buildSummaryState(currentCase) {
  const selectedOption = getSelectedCodeOption(currentCase);
  const alternatives = getAlternativeOptions(currentCase, selectedOption);
  const ecoPacket = selectedOption ? getEcoPacketForCode(currentCase, selectedOption.code) : null;
  const selectedEcoYear = getSelectedEcoYear(currentCase, selectedOption, ecoPacket);
  const selectedEcoYearPayload = getEcoYearPayload(ecoPacket, selectedEcoYear);
  const selectedSupportKey = currentCase ? appState.selectedSupportByCase[currentCase.case_id] || "" : "";
  const isEcoExpanded = currentCase ? appState.ecoExpandedByCase[currentCase.case_id] !== false : true;

  return {
    selectedOption,
    alternatives,
    ecoPacket,
    selectedEcoYear,
    selectedEcoYearPayload,
    isEcoExpanded,
    currencyRates: appState.currencyRates || null,
    selectedSupportKey,
  };
}

async function refreshCurrencyRates({ rerender = true } = {}) {
  try {
    const payload = await getJson("/api/eco-fee/currency-rates");
    appState.currencyRates = payload;
    if (rerender) {
      renderWorkspace();
    }
    return payload;
  } catch (error) {
    console.warn("Failed to load CBR rates for eco fee", error);
    return null;
  }
}

function setChatHistory(payload) {
  const caseId = payload?.case_id || "";
  if (!caseId) {
    return;
  }
  appState.chatByCase[caseId] = Array.isArray(payload.messages) ? payload.messages : [];
  appState.chatLoadedByCase[caseId] = true;
}

async function ensureChatLoaded(caseItem, { force = false } = {}) {
  if (!caseItem) {
    return false;
  }

  const caseId = caseItem.case_id;
  if (!force && appState.chatLoadedByCase[caseId]) {
    return false;
  }

  if (!force && chatHistoryPromises.has(caseId)) {
    return chatHistoryPromises.get(caseId);
  }

  const promise = getJson(`/api/agent-cli/history?case_id=${encodeURIComponent(caseId)}`)
    .then((payload) => {
      setChatHistory(payload);
      renderWorkspace();
      return true;
    })
    .catch((error) => {
      appState.chatByCase[caseId] = [
        {
          role: "model",
          text: `Не удалось подключить агента: ${error.message}`,
          created_at: new Date().toISOString(),
        },
      ];
      appState.chatLoadedByCase[caseId] = true;
      renderWorkspace();
      return false;
    })
    .finally(() => {
      chatHistoryPromises.delete(caseId);
    });

  chatHistoryPromises.set(caseId, promise);
  return promise;
}

function setBusy(element, isBusy) {
  if (!element) {
    return;
  }
  element.disabled = isBusy;
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  window.alert(message);
}

function updateSheetSelect(sheetNames, selectedSheet) {
  dom.sheetSelect.innerHTML = "";
  if (!sheetNames.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Лист не найден";
    dom.sheetSelect.append(option);
    return;
  }

  for (const sheetName of sheetNames) {
    const option = document.createElement("option");
    option.value = sheetName;
    option.textContent = sheetName;
    option.selected = sheetName === selectedSheet;
    dom.sheetSelect.append(option);
  }
}

function syncWorkbookOptionState() {
  appState.workbookAutoRunExtraRows = Boolean(dom.workbookAutoExtra?.checked);
  appState.workbookSkipInitialOcr = Boolean(dom.workbookSkipAutorun?.checked);
}

function clearWorkbookForm() {
  appState.workbookInspect = null;
  appState.pendingExportJobId = "";
  appState.pendingExportRootPath = "";
  appState.pendingWorkbookAutoRunCount = 0;
  clearWorkbookUploadProgress();
  appState.isWorkbookInspecting = false;
  appState.isWorkbookExporting = false;
  dom.workbookFile.value = "";
  dom.rowsInput.value = "2-20";
  dom.detectDuplicates.checked = true;
  dom.workbookAutoExtra.checked = false;
  dom.workbookSkipAutorun.checked = false;
  syncWorkbookOptionState();
  updateWorkbookFileName();
  clearWorkbookOverlay();
  updateSheetSelect([], "");
}

function ensureChat(caseItem) {
  if (!caseItem) {
    return [];
  }

  if (appState.chatByCase[caseItem.case_id]) {
    return appState.chatByCase[caseItem.case_id];
  }

  return [
    {
      role: "model",
      text: `Подключаю агента по кейсу ${caseItem.case_id}...`,
      created_at: new Date().toISOString(),
    },
  ];
}

function buildQuestions(caseItem) {
  if (!caseItem) {
    return [];
  }

  if (Array.isArray(caseItem.questions) && caseItem.questions.length) {
    return caseItem.questions
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .slice(0, 3);
  }

  if (Array.isArray(caseItem.question_items) && caseItem.question_items.length) {
    return caseItem.question_items
      .map((item) => String(item?.question ?? "").trim())
      .filter(Boolean)
      .slice(0, 3);
  }

  return [];
}

function setWorkspace(payload, { force = true } = {}) {
  const nextSignature = buildSignature(payload);
  const changed = nextSignature !== lastWorkspaceSignature;
  if (force || changed) {
    lastWorkspaceSignature = nextSignature;
    appState.workspace = payload;
  }
  return changed;
}

function setJobs(jobs, { force = true } = {}) {
  const nextSignature = buildSignature(jobs);
  const changed = nextSignature !== lastJobsSignature;
  if (force || changed) {
    lastJobsSignature = nextSignature;
    appState.jobs = jobs;
  }
  return changed;
}

function setActiveView(viewId) {
  appState.activeView = viewId;
}

function updateActionState() {
  const renderWorkspaceState = getWorkspaceForRender();
  const renderCurrentCase = renderWorkspaceState?.current_case || null;
  const hasCurrentCase = Boolean(renderCurrentCase);
  const hasRoots = Boolean(renderWorkspaceState?.roots?.length);
  const currentCaseId = getCurrentCaseId();
  const chatBusy = currentCaseId ? Boolean(appState.chatBusyByCase[currentCaseId]) : false;
  const canRunWorkbook = Boolean(appState.workbookInspect?.workbook_path) && appState.workbookInspect?.is_workbook_compatible;
  const itsBusy = Boolean(appState.isItsSessionBusy);
  const itsPendingStep = String(appState.itsSessionStatus?.pending_step || "");
  dom.saveExcelButton.disabled = !hasCurrentCase;
  dom.skipCaseButton.disabled = !hasCurrentCase;
  dom.runOcrButton.disabled = !hasCurrentCase;
  dom.prefetchButton.disabled = !hasRoots;
  dom.stopOcrButton.disabled = !hasActiveOcrActivity() || appState.isStoppingOcr;
  dom.rootSelect.disabled = !hasRoots;
  dom.deleteRootButton.disabled = !hasRoots || !renderWorkspaceState?.active_root_path;
  dom.toggleHelperButton.classList.toggle("is-active", Boolean(appState.areToolbarHintsExpanded));
  dom.toggleHelperButton.textContent = appState.areToolbarHintsExpanded ? "Скрыть подсказки" : "Подсказки";
  dom.runWorkbookButton.disabled =
    !canRunWorkbook || appState.isWorkbookInspecting || appState.isWorkbookExporting || appState.isWorkbookUploading;
  dom.openItsSettingsButton.disabled = itsBusy;
  dom.closeItsSettingsButton.disabled = itsBusy;
  dom.itsEnabledToggleButton.disabled = itsBusy || !appState.itsSessionStatus;
  dom.itsRefreshButton.disabled = itsBusy;
  dom.itsCheckAccessButton.disabled = itsBusy;
  dom.itsTestQueryButton.disabled = itsBusy;
  dom.itsDeleteSessionButton.disabled = itsBusy;
  dom.itsCancelLoginButton.disabled = itsBusy || !itsPendingStep;
  dom.itsStartLoginButton.disabled = itsBusy || !appState.itsForm.phone.trim();
  dom.itsSubmitCodeButton.disabled = itsBusy || itsPendingStep !== "code" || !appState.itsForm.code.trim();
  dom.itsSubmitPasswordButton.disabled = itsBusy || itsPendingStep !== "password" || !appState.itsForm.password.trim();
  dom.itsPhoneInput.disabled = itsBusy;
  dom.itsCodeInput.disabled = itsBusy || itsPendingStep !== "code";
  dom.itsPasswordInput.disabled = itsBusy || itsPendingStep !== "password";
  dom.itsTestCodeInput.disabled = itsBusy;
  dom.workbookFile.disabled = appState.isWorkbookInspecting || appState.isWorkbookExporting || appState.isWorkbookUploading;
  dom.sheetSelect.disabled =
    appState.isWorkbookInspecting || appState.isWorkbookExporting || appState.isWorkbookUploading || !appState.workbookInspect;
  dom.rowsInput.disabled = appState.isWorkbookInspecting || appState.isWorkbookExporting || appState.isWorkbookUploading;
  dom.detectDuplicates.disabled = appState.isWorkbookInspecting || appState.isWorkbookExporting || appState.isWorkbookUploading;
  dom.workbookAutoExtra.disabled = appState.isWorkbookExporting || appState.isWorkbookUploading;
  dom.workbookSkipAutorun.disabled = appState.isWorkbookExporting || appState.isWorkbookUploading;
  dom.chatInput.disabled = !hasCurrentCase || chatBusy;
  dom.chatSubmitButton.disabled = !hasCurrentCase || chatBusy;
  dom.chatSubmitButton.textContent = chatBusy ? "Думаю..." : "Отправить";
  dom.refreshWorkspaceButton.title = "Перечитать кейсы и статусы без нового запуска OCR/GPT";
  dom.runOcrButton.textContent =
    hasCurrentCase && currentCaseHasAiResult(renderCurrentCase) ? "Подобрать текущий заново" : "Подобрать текущий";
  dom.runOcrButton.title = "Запустить OCR/GPT только по открытому товару";
  dom.prefetchButton.textContent = `Подобрать ${BATCH_SIZE} подряд`;
  dom.prefetchButton.title = `Запустить OCR/GPT по текущему и еще ${Math.max(BATCH_SIZE - 1, 0)} следующим товарам`;
  dom.stopOcrButton.textContent = appState.isStoppingOcr ? "Останавливаю..." : "Остановить подбор";
  dom.stopOcrButton.title = "Остановить текущий OCR/GPT и batch-очередь";
  dom.skipCaseButton.title = "Перейти к следующему товару без записи результата";
  dom.saveExcelButton.title = "Пометить текущий товар как готовый и перейти дальше";
  dom.runWorkbookButton.textContent = appState.isWorkbookExporting
    ? "Создаю..."
    : appState.isWorkbookUploading && Number.isFinite(appState.workbookUploadProgress?.percent)
      ? `Загружаю ${Math.round(appState.workbookUploadProgress.percent)}%`
      : "Создать товары";
  dom.runWorkbookButton.title = canRunWorkbook
    ? `Создать товары из таблицы и ${appState.workbookSkipInitialOcr ? "не запускать подбор" : `запустить OCR по ${getWorkbookAutorunCount()} товарам`} автоматически`
    : "Сначала выбери подходящую таблицу с обязательными колонками";
}

function renderWorkspace() {
  const workspaceForRender = getWorkspaceForRender();
  const jobsForRender = getJobsForRender();

  renderToolbarHelper();
  renderRootSelect(dom.rootSelect, workspaceForRender);
  renderCounters(dom, workspaceForRender);
  renderCarousel(dom.rowCarousel, workspaceForRender);
  renderBatchStatus(dom.batchStatusBanner, jobsForRender, workspaceForRender);

  const currentCase = workspaceForRender?.current_case || null;
  const chatMessages = ensureChat(currentCase);
  const questions = buildQuestions(currentCase);

  renderImages(dom.imageGrid, currentCase);
  renderCaseMeta(dom, currentCase);
  renderAnalysis(dom.analysisContent, currentCase, questions, {
    expandedDetailedOcr: currentCase ? Boolean(appState.analysisDetailExpandedByCase[currentCase.case_id]) : false,
  });
  renderChat(dom.chatMessages, currentCase, chatMessages);
  renderQuestions(dom.modelQuestions, questions, {
    expanded: appState.areChatQuestionsExpanded,
  });
  const summaryState = buildSummaryState(currentCase);
  renderOutputStatusLine(dom.outputStatusLine, currentCase, summaryState);
  renderSummary(dom.outputCanvas, currentCase, summaryState);
  renderSourceTable(dom.sourceTableWrap, currentCase);
  renderModule0Status(dom.workbookStatus, appState.workbookInspect, jobsForRender, appState.workbookUploadProgress);
  const progressOverlayActive = renderCaseProgressOverlay(dom.caseProgressOverlay, currentCase);

  dom.workbookDrawer.classList.toggle("is-hidden", !appState.isWorkbookDrawerOpen);
  dom.toggleWorkbookButton.classList.toggle("is-active", appState.isWorkbookDrawerOpen);
  dom.toolbarHelper.classList.toggle("is-hidden", !appState.areToolbarHintsExpanded);
  dom.workspaceView.classList.toggle("is-hidden", appState.activeView !== "workspace");
  dom.tableView.classList.toggle("is-hidden", appState.activeView !== "table");
  dom.workspaceView.classList.toggle("is-chat-focus", Boolean(appState.isChatFocusMode));
  dom.workspaceView.classList.toggle("is-processing", Boolean(progressOverlayActive) && appState.activeView === "workspace");
  dom.tabWorkspaceButton.classList.toggle("is-active", appState.activeView === "workspace");
  dom.tabTableButton.classList.toggle("is-active", appState.activeView === "table");
  dom.focusChatButton.classList.toggle("is-active", Boolean(appState.isChatFocusMode));
  dom.focusChatButton.textContent = appState.isChatFocusMode ? "Обычный вид" : "На весь экран";
  dom.workbookOverlay.classList.toggle("is-hidden", !appState.workbookOverlay);
  if (appState.workbookOverlay) {
    dom.workbookOverlayTitle.textContent = appState.workbookOverlay.title || "Подбираем ТН ВЭД код";
    dom.workbookOverlayText.textContent = appState.workbookOverlay.text || "";
    dom.workbookOverlayExtra.classList.toggle("is-active", Boolean(appState.workbookOverlay.showExtra));
    dom.workbookOverlaySkip.classList.toggle("is-active", Boolean(appState.workbookOverlay.showSkip));
  } else {
    dom.workbookOverlayTitle.textContent = "Подбираем ТН ВЭД код";
    dom.workbookOverlayText.textContent = "Подготавливаем товары и запускаем OCR.";
    dom.workbookOverlayExtra.classList.remove("is-active");
    dom.workbookOverlaySkip.classList.remove("is-active");
  }
  renderWorkbookRulesModal();
  renderItsSessionModal();
  renderEcoDbEntryModal();
  updateActionState();
  void ensureChatLoaded(currentCase);
}

async function refreshWorkspace({ silent = false, rerender = true, force = true } = {}) {
  try {
    const payload = await getJson("/api/workspace");
    const changed = setWorkspace(payload, { force });
    if (rerender && (force || changed)) {
      renderWorkspace();
    }
    return { payload, changed };
  } catch (error) {
    if (!silent) {
      showError(error);
    }
    throw error;
  }
}

async function startBatchOcr(count, { confirmRestart = true } = {}) {
  if (confirmRestart && !confirmBatchGeneration()) {
    return false;
  }
  appState.hideBatchBanner = false;
  appState.forcedStoppedCaseIds = [];
  const payload = await postJson("/api/workspace/prefetch", { count });
  setWorkspace(payload);
  renderWorkspace();
  await refreshJobs({ silent: true });
  return true;
}

async function tryAdoptExportRoot() {
  if (!appState.pendingExportJobId || !appState.pendingExportRootPath) {
    return false;
  }

  const job = appState.jobs.find((item) => item.job_id === appState.pendingExportJobId);
  if (!job) {
    return false;
  }

  if (job.status === "completed") {
    try {
      const payload = await postJson("/api/workspace/root", {
        root_path: appState.pendingExportRootPath,
      });
      appState.pendingExportJobId = "";
      appState.pendingExportRootPath = "";
      setWorkspace(payload);
      appState.isWorkbookDrawerOpen = false;

      if (!appState.workbookSkipInitialOcr && appState.pendingWorkbookAutoRunCount > 0) {
        setWorkbookOverlay({
          title: "Подбираем ТН ВЭД код",
          text: `Создали товары. Запускаю OCR по ${appState.pendingWorkbookAutoRunCount} строкам.`,
          showExtra: appState.pendingWorkbookAutoRunCount > BATCH_SIZE,
          showSkip: false,
        });
        await startBatchOcr(appState.pendingWorkbookAutoRunCount, { confirmRestart: false });
      }

      return true;
    } finally {
      appState.pendingWorkbookAutoRunCount = 0;
      appState.isWorkbookExporting = false;
      clearWorkbookOverlay();
    }
  }

  if (job.status === "failed") {
    appState.pendingExportJobId = "";
    appState.pendingExportRootPath = "";
    appState.pendingWorkbookAutoRunCount = 0;
    appState.isWorkbookExporting = false;
    clearWorkbookOverlay();
  }

  return false;
}

async function refreshJobs({ silent = false, rerender = true, force = true } = {}) {
  try {
    const payload = await getJson("/api/jobs");
    const jobsChanged = setJobs(payload.jobs, { force });
    const workspaceChanged = await tryAdoptExportRoot();
    if (rerender && (force || jobsChanged || workspaceChanged)) {
      renderWorkspace();
    }
    return { payload, changed: force || jobsChanged || workspaceChanged };
  } catch (error) {
    if (!silent) {
      showError(error);
    }
    throw error;
  }
}

async function selectRoot(rootPath) {
  const payload = await postJson("/api/workspace/root", { root_path: rootPath });
  setWorkspace(payload);
  renderWorkspace();
}

async function selectCase(caseId) {
  const payload = await postJson("/api/workspace/current-case", { case_id: caseId });
  setWorkspace(payload);
  renderWorkspace();
}

async function saveToExcel() {
  const payload = await postJson("/api/workspace/save-excel", {});
  setWorkspace(payload);
  renderWorkspace();
}

async function skipCase() {
  const payload = await postJson("/api/workspace/skip", {});
  setWorkspace(payload);
  renderWorkspace();
}

async function runOcr() {
  const currentCase = getCurrentCase();
  if (!currentCase) {
    throw new Error("Сначала выбери кейс.");
  }
  if (!confirmCurrentGeneration()) {
    return;
  }
  const controller = new AbortController();
  appState.hideBatchBanner = false;
  appState.forcedStoppedCaseIds = [];
  appState.localSingleRunCaseId = currentCase.case_id;
  patchWorkspaceCaseState([currentCase.case_id], {
    ocr_status: "running",
    background_status: "running",
  });
  renderWorkspace();
  activeOcrAbortController = controller;
  try {
    const payload = await postJson(
      "/api/workspace/run-ocr",
      {
        case_id: currentCase.case_id,
      },
      { signal: controller.signal }
    );
    setWorkspace(payload);
    renderWorkspace();
    await refreshJobs({ silent: true });
  } catch (error) {
    if (error?.name === "AbortError") {
      return;
    }
    throw error;
  } finally {
    appState.localSingleRunCaseId = "";
    if (activeOcrAbortController === controller) {
      activeOcrAbortController = null;
    }
    renderWorkspace();
  }
}

async function prefetchCases() {
  await startBatchOcr(BATCH_SIZE);
}

async function stopOcr() {
  const activeCaseIds = collectActiveOcrCaseIds();
  appState.isStoppingOcr = true;
  appState.forcedStoppedCaseIds = activeCaseIds;
  appState.localSingleRunCaseId = "";
  appState.hideBatchBanner = true;
  patchWorkspaceCaseState(activeCaseIds, {
    ocr_status: "cancelled",
    prefetch_status: "cancelled",
    background_status: "cancelled",
  });
  if (dom.batchStatusBanner) {
    dom.batchStatusBanner.classList.add("is-hidden");
    dom.batchStatusBanner.textContent = "";
    dom.batchStatusBanner.dataset.state = "idle";
    delete dom.batchStatusBanner.dataset.jobId;
    delete dom.batchStatusBanner.dataset.hideAt;
    if (dom.batchStatusBanner._hideTimerId) {
      window.clearTimeout(dom.batchStatusBanner._hideTimerId);
      dom.batchStatusBanner._hideTimerId = null;
    }
  }
  renderWorkspace();
  try {
    if (activeOcrAbortController) {
      activeOcrAbortController.abort();
      activeOcrAbortController = null;
    }
    const payload = await postJson("/api/workspace/stop-ocr", {});
    setWorkspace(payload);
    appState.forcedStoppedCaseIds = [];
    renderWorkspace();
    await refreshJobs({ silent: true });
  } finally {
    appState.isStoppingOcr = false;
    clearWorkbookOverlay();
    renderWorkspace();
  }
}

async function inspectWorkbook({ withCurrentSheet = false } = {}) {
  const formData = new FormData();
  const file = dom.workbookFile.files[0];
  const rememberedPath = appState.workbookInspect?.workbook_path || "";
  const hasNewFileSelection = Boolean(file && (!rememberedPath || !rememberedPath.endsWith(file.name)));
  let isUploadingFile = false;

  if (withCurrentSheet && rememberedPath) {
    formData.append("workbook_path", rememberedPath);
  } else if (hasNewFileSelection) {
    formData.append("workbook_file", file);
    isUploadingFile = true;
  } else if (rememberedPath) {
    formData.append("workbook_path", rememberedPath);
  } else if (file) {
    formData.append("workbook_file", file);
    isUploadingFile = true;
  } else {
    throw new Error("Выбери Excel-файл.");
  }

  if (withCurrentSheet && dom.sheetSelect.value) {
    formData.append("sheet_name", dom.sheetSelect.value);
  }

  appState.isWorkbookInspecting = true;
  if (isUploadingFile) {
    appState.isWorkbookUploading = true;
    setWorkbookUploadProgress({
      isActive: true,
      fileName: file?.name || "Excel",
      loaded: 0,
      total: Number(file?.size || 0),
      percent: 0,
    });
  } else {
    clearWorkbookUploadProgress();
  }
  renderWorkspace();
  try {
    const payload = isUploadingFile
      ? await postFormWithProgress("/api/workbook/inspect", formData, {
          onProgress(event) {
            const total = Number(event.total || file?.size || 0);
            const loaded = Number(event.loaded || 0);
            const percent = total > 0 ? (loaded / total) * 100 : 0;
            setWorkbookUploadProgress({
              isActive: true,
              fileName: file?.name || "Excel",
              loaded,
              total,
              percent,
            });
            renderWorkspace();
          },
        })
      : await postForm("/api/workbook/inspect", formData);
    appState.workbookInspect = payload;
    if (!withCurrentSheet) {
      openWorkbookRulesModal(payload);
    }
    if (!payload?.is_workbook_compatible) {
      resetWorkbookFileSelection();
    }
    updateSheetSelect(payload.sheet_names, payload.selected_sheet);
    renderWorkspace();
  } finally {
    appState.isWorkbookInspecting = false;
    clearWorkbookUploadProgress();
    renderWorkspace();
  }
}

async function exportWorkbook() {
  const inspectPayload = appState.workbookInspect;
  const workbookPath = inspectPayload?.workbook_path || "";
  if (!workbookPath) {
    throw new Error("Сначала выбери и проверь Excel-файл.");
  }
  if (inspectPayload && !inspectPayload.is_workbook_compatible) {
    const details = Array.isArray(inspectPayload.validation_errors) ? inspectPayload.validation_errors.join(" ") : "";
    throw new Error(`Файл не готов к выгрузке. ${details || "Исправьте структуру таблицы и выберите файл заново."}`);
  }
  if (!dom.rowsInput.value.trim()) {
    throw new Error("Обязательно укажите строки для создания товаров.");
  }

  const autoRunCount = appState.workbookSkipInitialOcr ? 0 : getWorkbookAutorunCount();
  appState.isWorkbookExporting = true;
  appState.pendingWorkbookAutoRunCount = autoRunCount;
  setWorkbookOverlay({
    title: autoRunCount > 0 ? "Подбираем ТН ВЭД код" : "Подготавливаем товары",
    text:
      autoRunCount > 0
        ? `Создаю товары из таблицы и затем запущу OCR по ${autoRunCount} строкам.`
        : "Создаю товары из таблицы без автоматического подбора.",
    showExtra: appState.workbookAutoRunExtraRows,
    showSkip: appState.workbookSkipInitialOcr,
  });
  renderWorkspace();

  try {
    const payload = await postJson("/api/workbook/export", {
      workbook_path: workbookPath,
      sheet_name: dom.sheetSelect.value,
      rows: dom.rowsInput.value.trim() || "2-20",
      output_dir: null,
      detect_duplicates: dom.detectDuplicates.checked,
      header_row: 1,
    });

    appState.pendingExportJobId = payload.job_id || "";
    appState.pendingExportRootPath = payload.payload?.output_dir || "";
    await refreshJobs({ silent: true });
    renderWorkspace();
  } catch (error) {
    appState.isWorkbookExporting = false;
    appState.pendingWorkbookAutoRunCount = 0;
    clearWorkbookOverlay();
    renderWorkspace();
    throw error;
  }
}

async function clearWorkbook() {
  const workbookPath = appState.workbookInspect?.workbook_path || "";
  if (workbookPath) {
    await postJson("/api/workbook/clear", {
      workbook_path: workbookPath,
    });
  }
  clearWorkbookForm();
  renderWorkspace();
}

async function deleteCurrentRoot() {
  const rootPath = appState.workspace?.active_root_path || dom.rootSelect.value;
  if (!rootPath) {
    throw new Error("Нет выбранной таблицы для удаления.");
  }

  const confirmed = window.confirm("Удалить текущую таблицу и все case-папки без возможности восстановления?");
  if (!confirmed) {
    return;
  }

  const payload = await postJson("/api/workspace/delete-root", {
    root_path: rootPath,
  });
  setWorkspace(payload);
  renderWorkspace();
}

function openImageModal(imageUrl) {
  dom.imageModalContent.src = imageUrl;
  dom.imageModal.classList.remove("is-hidden");
}

function closeImageModal() {
  dom.imageModal.classList.add("is-hidden");
  dom.imageModalContent.src = "";
}

function openEcoDbEntryModal(payload) {
  appState.ecoDbEntryModal = payload || null;
  renderWorkspace();
}

function closeEcoDbEntryModal() {
  appState.ecoDbEntryModal = null;
  renderWorkspace();
}

function renderEcoDbEntryModal() {
  if (!dom.ecoDbEntryModal || !dom.ecoDbEntryContent) {
    return;
  }

  const modalState = appState.ecoDbEntryModal || null;
  const currentCase = getCurrentCase();
  const isVisible = Boolean(modalState && currentCase?.case_id && modalState.caseId === currentCase.case_id);

  dom.ecoDbEntryModal.classList.toggle("is-hidden", !isVisible);
  if (!isVisible) {
    dom.ecoDbEntryContent.innerHTML = "";
    return;
  }

  if (modalState.mode === "list") {
    const entries = Array.isArray(modalState.entries) ? modalState.entries : [];
    dom.ecoDbEntryContent.innerHTML = `
      <div class="eco-db-modal-kicker">Экосбор / строки БД</div>
      <div class="eco-db-modal-title">${escapeInlineHtml(modalState.matchTitle || "Совпадение из базы")}</div>
      <div class="eco-db-modal-meta">
        Все строки из базы для кода ${escapeInlineHtml(modalState.selectedCode || "—")} · ${escapeInlineHtml(String(modalState.year || "—"))} год · ${escapeInlineHtml(String(entries.length))} шт.
      </div>
      <div class="eco-db-modal-list">
        ${
          entries.length
            ? entries
                .map((entry) => {
                  const footnotes = Array.isArray(entry?.footnotes) ? entry.footnotes : [];
                  const footnoteMarkers = footnotes
                    .map((item) => String(item?.marker || "").trim())
                    .filter(Boolean)
                    .join(" ");
                  return `
                    <article class="eco-db-modal-row">
                      <div class="eco-db-modal-row-main">
                        <div class="eco-db-modal-row-title">${escapeInlineHtml(entry?.row_name || entry?.tnved_name || "Наименование в строке не заполнено")}</div>
                        <div class="eco-db-modal-row-meta">
                          строка ${escapeInlineHtml(String(entry?.source_row || "—"))} · код ${escapeInlineHtml(entry?.tnved_digits || entry?.tnved_raw || "—")}
                          ${entry?.okpd2 ? ` · ОКПД2 ${escapeInlineHtml(entry.okpd2)}` : ""}
                        </div>
                        ${footnoteMarkers ? `<div class="eco-db-modal-row-footnotes">Сноски: ${escapeInlineHtml(footnoteMarkers)}</div>` : ""}
                      </div>
                      <button
                        class="eco-db-preview-button"
                        type="button"
                        data-eco-entry-open="true"
                        data-eco-match-key="${escapeInlineHtml(modalState.matchKey || "")}"
                        data-eco-entry-key="${escapeInlineHtml(entry?.entry_key || "")}"
                      >
                        Подробнее
                      </button>
                    </article>
                  `;
                })
                .join("")
            : `<div class="output-body is-muted">Строки БД для этого совпадения не найдены.</div>`
        }
      </div>
    `;
    return;
  }

  const entry = modalState.entry || {};
  const footnotes = Array.isArray(entry.footnotes) ? entry.footnotes : [];
  const fields = [
    ["Строка в книге", entry.source_row || "—"],
    ["Код в ячейке", entry.tnved_raw || "—"],
    ["Нормализованный код", entry.tnved_digits || "—"],
    [
      "Группа экосбора",
      entry.eco_group_code ? `${entry.eco_group_code} · ${entry.eco_group_name || "—"}` : entry.eco_group_name || "—",
    ],
    ["Наименование строки", entry.row_name || "—"],
    ["Наименование ТН ВЭД", entry.tnved_name || "—"],
    ["ОКПД2", entry.okpd2 || "—"],
  ];

  dom.ecoDbEntryContent.innerHTML = `
    <div class="eco-db-modal-kicker">Экосбор / строка БД</div>
    <div class="eco-db-modal-title">${escapeInlineHtml(entry.row_name || entry.tnved_name || "Строка без названия")}</div>
    <div class="eco-db-modal-meta">
      Проверка для кода ${escapeInlineHtml(modalState.selectedCode || "—")} · ${escapeInlineHtml(modalState.matchTitle || "Совпадение из базы")} · ${escapeInlineHtml(String(modalState.year || "—"))} год
    </div>
    ${
      Array.isArray(modalState.entries) && modalState.entries.length
        ? `
          <div class="eco-db-modal-actions">
            <button class="eco-inline-button" type="button" data-eco-entry-back-list="true">Ко всем строкам БД</button>
          </div>
        `
        : ""
    }
    <div class="eco-db-modal-grid">
      ${fields
        .map(
          ([label, value]) => `
            <div class="eco-db-modal-field">
              <span>${escapeInlineHtml(label)}</span>
              <strong>${escapeInlineHtml(String(value || "—"))}</strong>
            </div>
          `
        )
        .join("")}
    </div>
    ${
      footnotes.length
        ? `
          <div class="eco-subtitle">Сноски по этой строке (${escapeInlineHtml(String(footnotes.length))})</div>
          <div class="eco-footnote-box eco-footnote-box-modal">
            <div class="eco-footnote-list">
              ${footnotes
                .map(
                  (item) => `
                    <div class="eco-footnote-item">
                      <span class="eco-footnote-marker">${escapeInlineHtml(item.marker || "")}</span>
                      <span>${escapeInlineHtml(item.text || "Текст сноски в книге не найден.")}</span>
                    </div>
                  `
                )
                .join("")}
            </div>
          </div>
        `
        : ""
    }
  `;
}

async function runItsSessionAction(action) {
  appState.isItsSessionBusy = true;
  renderWorkspace();
  try {
    if (action === "refresh") {
      await refreshItsSessionStatus();
      return;
    }

    if (action === "start-login") {
      const payload = await postJson("/api/its-session/start", {
        phone: appState.itsForm.phone.trim(),
      });
      setItsSessionStatus(payload);
      appState.itsAccessCheck = null;
      appState.itsTestQuery = null;
      appState.itsForm.code = "";
      appState.itsForm.password = "";
      renderWorkspace();
      return;
    }

    if (action === "submit-code") {
      const payload = await postJson("/api/its-session/code", {
        code: appState.itsForm.code.trim(),
      });
      setItsSessionStatus(payload);
      if (payload.pending_step !== "code") {
        appState.itsForm.code = "";
      }
      if (!payload.pending_step) {
        appState.itsForm.password = "";
      }
      renderWorkspace();
      return;
    }

    if (action === "submit-password") {
      const payload = await postJson("/api/its-session/password", {
        password: appState.itsForm.password,
      });
      setItsSessionStatus(payload);
      appState.itsForm.password = "";
      renderWorkspace();
      return;
    }

    if (action === "cancel-login") {
      const payload = await postJson("/api/its-session/cancel", {});
      setItsSessionStatus(payload);
      appState.itsForm.code = "";
      appState.itsForm.password = "";
      renderWorkspace();
      return;
    }

    if (action === "delete-session") {
      const confirmed = window.confirm("Удалить текущую ITS session и переместить файлы в quarantine?");
      if (!confirmed) {
        return;
      }
      const payload = await postJson("/api/its-session/delete", {});
      setItsSessionStatus(payload);
      appState.itsAccessCheck = null;
      appState.itsTestQuery = null;
      renderWorkspace();
      return;
    }

    if (action === "toggle-enabled") {
      const nextEnabled = !Boolean(appState.itsSessionStatus?.its_enabled);
      const payload = await postJson("/api/its-session/enabled", {
        enabled: nextEnabled,
      });
      setItsSessionStatus(payload);
      appState.itsAccessCheck = null;
      appState.itsTestQuery = null;
      renderWorkspace();
      return;
    }

    if (action === "check-access") {
      const payload = await postJson("/api/its-session/check-access", {});
      applyItsDiagnostic(payload);
      renderWorkspace();
      return;
    }

    if (action === "test-query") {
      const payload = await postJson("/api/its-session/test-query", {
        code: appState.itsForm.testCode.trim(),
      });
      applyItsDiagnostic(payload);
      renderWorkspace();
    }
  } finally {
    appState.isItsSessionBusy = false;
    renderWorkspace();
  }
}

function bindEventHandlers() {
  dom.openItsSettingsButton.addEventListener("click", async () => {
    try {
      await openItsSettingsModal();
    } catch (error) {
      showError(error);
    }
  });

  dom.closeItsSettingsButton.addEventListener("click", closeItsSettingsModal);

  dom.itsSettingsModal.addEventListener("click", (event) => {
    if (event.target === dom.itsSettingsModal) {
      closeItsSettingsModal();
    }
  });

  dom.itsPhoneInput.addEventListener("input", () => {
    appState.itsForm.phone = dom.itsPhoneInput.value;
    updateActionState();
  });

  dom.itsCodeInput.addEventListener("input", () => {
    appState.itsForm.code = dom.itsCodeInput.value;
    updateActionState();
  });

  dom.itsPasswordInput.addEventListener("input", () => {
    appState.itsForm.password = dom.itsPasswordInput.value;
    updateActionState();
  });

  dom.itsTestCodeInput.addEventListener("input", () => {
    appState.itsForm.testCode = dom.itsTestCodeInput.value;
    updateActionState();
  });

  dom.itsRefreshButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("refresh");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsEnabledToggleButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("toggle-enabled");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsCheckAccessButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("check-access");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsTestQueryButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("test-query");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsCancelLoginButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("cancel-login");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsDeleteSessionButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("delete-session");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsStartLoginButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("start-login");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsSubmitCodeButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("submit-code");
    } catch (error) {
      showError(error);
    }
  });

  dom.itsSubmitPasswordButton.addEventListener("click", async () => {
    try {
      await runItsSessionAction("submit-password");
    } catch (error) {
      showError(error);
    }
  });

  dom.toggleWorkbookButton.addEventListener("click", () => {
    appState.isWorkbookDrawerOpen = !appState.isWorkbookDrawerOpen;
    renderWorkspace();
  });

  dom.toggleHelperButton.addEventListener("click", () => {
    appState.areToolbarHintsExpanded = !appState.areToolbarHintsExpanded;
    renderWorkspace();
  });

  dom.tabWorkspaceButton.addEventListener("click", () => {
    setActiveView("workspace");
    renderWorkspace();
  });

  dom.tabTableButton.addEventListener("click", () => {
    setActiveView("table");
    renderWorkspace();
  });

  dom.focusChatButton.addEventListener("click", () => {
    appState.isChatFocusMode = !appState.isChatFocusMode;
    renderWorkspace();
  });

  dom.refreshWorkspaceButton.addEventListener("click", async () => {
    await refreshWorkspace();
    await refreshJobs({ silent: true });
  });

  dom.deleteRootButton.addEventListener("click", async () => {
    setBusy(dom.deleteRootButton, true);
    try {
      await deleteCurrentRoot();
      clearWorkbookForm();
    } finally {
      setBusy(dom.deleteRootButton, false);
    }
  });

  dom.runOcrButton.addEventListener("click", async () => {
    setBusy(dom.runOcrButton, true);
    try {
      await runOcr();
    } finally {
      setBusy(dom.runOcrButton, false);
    }
  });

  dom.rootSelect.addEventListener("change", async () => {
    if (!dom.rootSelect.value) {
      return;
    }
    await selectRoot(dom.rootSelect.value);
    await refreshJobs({ silent: true });
  });

  dom.rowCarousel.addEventListener("click", async (event) => {
    const button = event.target.closest(".carousel-chip");
    if (!button) {
      return;
    }
    await selectCase(button.dataset.caseId);
  });

  dom.imageGrid.addEventListener("click", (event) => {
    const tile = event.target.closest(".image-tile");
    if (!tile) {
      return;
    }
    openImageModal(tile.dataset.imageUrl);
  });

  dom.imageModal.addEventListener("click", (event) => {
    if (event.target === dom.imageModal) {
      closeImageModal();
    }
  });

  dom.closeImageModalButton.addEventListener("click", closeImageModal);
  dom.closeEcoDbEntryModalButton?.addEventListener("click", closeEcoDbEntryModal);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && appState.ecoDbEntryModal) {
      closeEcoDbEntryModal();
      return;
    }
    if (event.key === "Escape" && appState.isItsModalOpen) {
      closeItsSettingsModal();
      return;
    }
    if (event.key === "Escape" && !dom.imageModal.classList.contains("is-hidden")) {
      closeImageModal();
    }
  });

  dom.saveExcelButton.addEventListener("click", async () => {
    setBusy(dom.saveExcelButton, true);
    try {
      await saveToExcel();
    } finally {
      setBusy(dom.saveExcelButton, false);
    }
  });

  dom.skipCaseButton.addEventListener("click", async () => {
    setBusy(dom.skipCaseButton, true);
    try {
      await skipCase();
    } finally {
      setBusy(dom.skipCaseButton, false);
    }
  });

  dom.prefetchButton.addEventListener("click", async () => {
    setBusy(dom.prefetchButton, true);
    try {
      await prefetchCases();
    } finally {
      setBusy(dom.prefetchButton, false);
    }
  });

  dom.stopOcrButton.addEventListener("click", async () => {
    setBusy(dom.stopOcrButton, true);
    try {
      await stopOcr();
    } finally {
      setBusy(dom.stopOcrButton, false);
    }
  });

  dom.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = dom.chatInput.value.trim();
    const currentCase = getCurrentCase();
    if (!text || !currentCase) {
      return;
    }
    const caseId = currentCase.case_id;
    const currentMessages = Array.isArray(appState.chatByCase[caseId]) ? appState.chatByCase[caseId] : [];
    appState.chatByCase[caseId] = [
      ...currentMessages,
      {
        role: "user",
        text,
        created_at: new Date().toISOString(),
      },
      {
        role: "model",
        text: "Агент читает кейс и собирает ответ...",
        created_at: new Date().toISOString(),
      },
    ];
    appState.chatBusyByCase[caseId] = true;
    dom.chatInput.value = "";
    renderWorkspace();

    try {
      const payload = await postJson("/api/agent-cli/message", {
        case_id: caseId,
        message: text,
      });
      setChatHistory(payload);
    } catch (error) {
      appState.chatByCase[caseId] = [
        ...currentMessages,
        {
          role: "user",
          text,
          created_at: new Date().toISOString(),
        },
        {
          role: "model",
          text: `Агент вернул ошибку: ${error.message}`,
          created_at: new Date().toISOString(),
        },
      ];
      appState.chatLoadedByCase[caseId] = true;
    } finally {
      appState.chatBusyByCase[caseId] = false;
      renderWorkspace();
    }
  });

  dom.chatInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    dom.chatForm.requestSubmit();
  });

  dom.modelQuestions.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-question-toggle]");
    if (toggle) {
      appState.areChatQuestionsExpanded = !appState.areChatQuestionsExpanded;
      renderWorkspace();
      return;
    }

    const shortcut = event.target.closest("[data-question-shortcut]");
    if (!shortcut) {
      return;
    }

    const shortcutValue = shortcut.dataset.questionShortcut || "";
    if (!shortcutValue) {
      return;
    }

    dom.chatInput.value = shortcutValue;
    dom.chatInput.focus();
  });

  dom.analysisContent.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-analysis-toggle]");
    if (!toggle) {
      return;
    }
    const currentCase = getCurrentCase();
    if (!currentCase?.case_id) {
      return;
    }
    appState.analysisDetailExpandedByCase[currentCase.case_id] = !appState.analysisDetailExpandedByCase[currentCase.case_id];
    renderWorkspace();
  });

  dom.runWorkbookButton.addEventListener("click", async () => {
    setBusy(dom.runWorkbookButton, true);
    try {
      await exportWorkbook();
    } finally {
      setBusy(dom.runWorkbookButton, false);
    }
  });

  dom.sheetSelect.addEventListener("change", async () => {
    if (!appState.workbookInspect?.workbook_path) {
      return;
    }
    await inspectWorkbook({ withCurrentSheet: true });
  });

  dom.workbookFile.addEventListener("change", async () => {
    appState.workbookInspect = null;
    closeWorkbookRulesModal();
    updateWorkbookFileName();
    renderWorkspace();
    if (!dom.workbookFile.files?.length) {
      return;
    }
    try {
      await inspectWorkbook();
    } catch (error) {
      resetWorkbookFileSelection();
      showError(error);
    }
  });

  dom.closeWorkbookRulesButton.addEventListener("click", () => {
    closeWorkbookRulesModal();
    renderWorkspace();
  });

  dom.ackWorkbookRulesButton.addEventListener("click", () => {
    closeWorkbookRulesModal();
    renderWorkspace();
  });

  dom.workbookRulesModal.addEventListener("click", (event) => {
    if (event.target === dom.workbookRulesModal) {
      closeWorkbookRulesModal();
      renderWorkspace();
    }
  });

  dom.ecoDbEntryModal?.addEventListener("click", (event) => {
    if (event.target === dom.ecoDbEntryModal) {
      closeEcoDbEntryModal();
    }
  });

  dom.workbookAutoExtra.addEventListener("change", () => {
    syncWorkbookOptionState();
    renderWorkspace();
  });

  dom.openWorkbookRulesButton.addEventListener("click", () => {
    openWorkbookRulesModal(appState.workbookInspect || null);
    renderWorkspace();
  });

  dom.workbookSkipAutorun.addEventListener("change", () => {
    syncWorkbookOptionState();
    renderWorkspace();
  });

  dom.outputCanvas.addEventListener("click", async (event) => {
    const codeButton = event.target.closest("[data-code-option-key]");
    if (codeButton) {
      const currentCase = getCurrentCase();
      if (!currentCase) {
        return;
      }
      appState.ecoDbEntryModal = null;
      appState.selectedCodeByCase[currentCase.case_id] = codeButton.dataset.codeOptionKey;
      renderWorkspace();
      return;
    }

    const supportButton = event.target.closest("[data-support-key]");
    if (supportButton) {
      const currentCase = getCurrentCase();
      if (!currentCase) {
        return;
      }
      const supportKey = supportButton.dataset.supportKey || "";
      const currentKey = appState.selectedSupportByCase[currentCase.case_id] || "";
      appState.selectedSupportByCase[currentCase.case_id] = currentKey === supportKey ? "" : supportKey;
      renderWorkspace();
      return;
    }

    const ecoYearButton = event.target.closest("[data-eco-year]");
    if (ecoYearButton) {
      const currentCase = getCurrentCase();
      const selectedOption = getSelectedCodeOption(currentCase);
      if (!currentCase || !selectedOption) {
        return;
      }
      const ecoPacket = getEcoPacketForCode(currentCase, selectedOption.code);
      if (!ecoPacket) {
        return;
      }
      const supportedYears = Array.isArray(ecoPacket.supported_years) ? ecoPacket.supported_years : [];
      const nextYear = Number(ecoYearButton.dataset.ecoYear || 0);
      if (!supportedYears.includes(nextYear)) {
        return;
      }
      appState.ecoDbEntryModal = null;
      appState.selectedEcoYearByCaseCode[`${currentCase.case_id}|${selectedOption.code}`] = nextYear;
      renderWorkspace();
      return;
    }

    const ecoEntryButton = event.target.closest("[data-eco-entry-open]");
    if (ecoEntryButton) {
      const currentCase = getCurrentCase();
      const summaryState = buildSummaryState(currentCase);
      const matches = Array.isArray(summaryState?.selectedEcoYearPayload?.matches)
        ? summaryState.selectedEcoYearPayload.matches
        : [];
      const matchKey = String(ecoEntryButton.dataset.ecoMatchKey || "");
      const entryKey = String(ecoEntryButton.dataset.ecoEntryKey || "");
      const match = matches.find((item) => String(item?.selection_key || "") === matchKey) || null;
      const dbEntries = Array.isArray(match?.db_entries) ? match.db_entries : [];
      const entry = dbEntries.find((item) => String(item?.entry_key || "") === entryKey) || null;
      if (!currentCase || !match || !entry) {
        return;
      }
      openEcoDbEntryModal({
        mode: "entry",
        caseId: currentCase.case_id,
        year: summaryState.selectedEcoYear,
        selectedCode: summaryState.selectedOption?.code || "",
        matchTitle: match.eco_group_name || "",
        matchKey,
        entries: dbEntries,
        entry,
      });
      return;
    }

    const ecoEntriesAllButton = event.target.closest("[data-eco-entry-open-all]");
    if (ecoEntriesAllButton) {
      const currentCase = getCurrentCase();
      const summaryState = buildSummaryState(currentCase);
      const matches = Array.isArray(summaryState?.selectedEcoYearPayload?.matches)
        ? summaryState.selectedEcoYearPayload.matches
        : [];
      const matchKey = String(ecoEntriesAllButton.dataset.ecoMatchKey || "");
      const match = matches.find((item) => String(item?.selection_key || "") === matchKey) || null;
      const dbEntries = Array.isArray(match?.db_entries) ? match.db_entries : [];
      if (!currentCase || !match || !dbEntries.length) {
        return;
      }
      openEcoDbEntryModal({
        mode: "list",
        caseId: currentCase.case_id,
        year: summaryState.selectedEcoYear,
        selectedCode: summaryState.selectedOption?.code || "",
        matchTitle: match.eco_group_name || "",
        matchKey,
        entries: dbEntries,
      });
      return;
    }

    const ecoEntryBackButton = event.target.closest("[data-eco-entry-back-list]");
    if (ecoEntryBackButton) {
      const modalState = appState.ecoDbEntryModal || null;
      if (!modalState?.caseId || !Array.isArray(modalState.entries)) {
        return;
      }
      openEcoDbEntryModal({
        mode: "list",
        caseId: modalState.caseId,
        year: modalState.year,
        selectedCode: modalState.selectedCode || "",
        matchTitle: modalState.matchTitle || "",
        matchKey: modalState.matchKey || "",
        entries: modalState.entries,
      });
      return;
    }

    const ecoToggleButton = event.target.closest("[data-eco-toggle]");
    if (ecoToggleButton) {
      const currentCase = getCurrentCase();
      if (!currentCase) {
        return;
      }
      appState.ecoDbEntryModal = null;
      const currentValue = appState.ecoExpandedByCase[currentCase.case_id] !== false;
      appState.ecoExpandedByCase[currentCase.case_id] = !currentValue;
      renderWorkspace();
      return;
    }
  });
}

async function poll() {
  if (pollInFlight) {
    return;
  }

  if (document.hidden) {
    return;
  }

  pollInFlight = true;
  try {
    const jobsResult = await refreshJobs({ silent: true, rerender: false, force: false });
    const workspaceResult = await refreshWorkspace({ silent: true, rerender: false, force: false });
    if (jobsResult.changed || workspaceResult.changed) {
      renderWorkspace();
    }
  } catch (error) {
    console.error(error);
  } finally {
    pollInFlight = false;
  }
}

async function bootstrap() {
  await ensureAuthenticated();
  bindEventHandlers();
  setActiveView(appState.activeView || "workspace");
  updateWorkbookFileName();
  syncWorkbookOptionState();
  updateSheetSelect([], "");
  renderWorkspace();

  await refreshWorkspace();
  await refreshJobs({ silent: true });
  await refreshCurrencyRates({ rerender: true });

  window.setInterval(poll, 4000);
}

bootstrap().catch((error) => {
  console.error(error);
  showError(error);
});
