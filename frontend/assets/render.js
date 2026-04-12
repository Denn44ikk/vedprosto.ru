function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function multiline(value) {
  return escapeHtml(value || "—").replaceAll("\n", "<br />");
}

const BATCH_BANNER_TERMINAL_TTL_MS = 15_000;

function clearBatchBannerHideTimer(target) {
  if (target?._hideTimerId) {
    window.clearTimeout(target._hideTimerId);
    target._hideTimerId = null;
  }
}

function hideBatchBanner(target) {
  clearBatchBannerHideTimer(target);
  target.classList.add("is-hidden");
  target.textContent = "";
  target.dataset.state = "idle";
  delete target.dataset.jobId;
  delete target.dataset.hideAt;
}

function getDisplayActivityStatus(caseItem) {
  const ocrStatus = String(caseItem?.ocr_status || "").toLowerCase();
  if (["queued", "running", "cancelling", "cancelled", "error"].includes(ocrStatus)) {
    return ocrStatus;
  }

  const prefetchStatus = String(caseItem?.prefetch_status || "").toLowerCase();
  if (["queued", "running", "cancelling", "completed", "cancelled", "error"].includes(prefetchStatus)) {
    return prefetchStatus;
  }

  if (["completed"].includes(ocrStatus)) {
    return ocrStatus;
  }

  return "";
}

function reviewClass(caseItem) {
  if (caseItem.is_current) {
    return "is-current";
  }
  if (caseItem.review_status === "saved") {
    return "is-saved";
  }
  if (caseItem.review_status === "skipped") {
    return "is-skipped";
  }
  const activityStatus = getDisplayActivityStatus(caseItem);
  if (activityStatus === "running") {
    return "is-running";
  }
  if (activityStatus === "queued") {
    return "is-running";
  }
  if (activityStatus === "cancelling") {
    return "is-running";
  }
  if (activityStatus === "completed") {
    return "is-prefetched";
  }
  if (activityStatus === "cancelled") {
    return "is-error";
  }
  if (activityStatus === "error") {
    return "is-error";
  }
  return "is-pending";
}

function prefetchLabelMeta(caseItem) {
  const activityStatus = getDisplayActivityStatus(caseItem);
  if (activityStatus === "queued") {
    return { text: "GPT ждёт", className: "is-queued", spinner: true };
  }
  if (activityStatus === "running") {
    return { text: "GPT", className: "is-running", spinner: true };
  }
  if (activityStatus === "cancelling") {
    return { text: "STOP...", className: "is-cancelling", spinner: true };
  }
  if (activityStatus === "completed") {
    return { text: "GPT OK", className: "is-completed", spinner: false };
  }
  if (activityStatus === "cancelled") {
    return { text: "STOP", className: "is-cancelled", spinner: false };
  }
  if (activityStatus === "error") {
    return { text: "ERROR", className: "is-error", spinner: false };
  }
  if (caseItem.review_status === "saved") {
    return { text: "готово", className: "is-saved", spinner: false };
  }
  if (caseItem.review_status === "skipped") {
    return { text: "пропуск", className: "is-skipped", spinner: false };
  }
  return null;
}

function buildBatchScopeLabel(trackedCases, fallbackCount = 0) {
  if (!trackedCases.length) {
    return fallbackCount === 1 ? "1 товар" : `${fallbackCount} товаров`;
  }

  const rowNumbers = trackedCases
    .map((item) => Number(item?.row_number || 0))
    .filter((item) => Number.isFinite(item) && item > 0);

  if (rowNumbers.length === trackedCases.length) {
    const first = Math.min(...rowNumbers);
    const last = Math.max(...rowNumbers);
    return first === last ? `строка ${first}` : `строки ${first}-${last}`;
  }

  return trackedCases.length === 1 ? "1 товар" : `${trackedCases.length} товаров`;
}

export function renderRootSelect(select, workspace) {
  const roots = workspace?.roots || [];
  const activeRootPath = workspace?.active_root_path || "";
  select.innerHTML = "";

  if (!roots.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Папка кейсов не найдена";
    select.append(option);
    return;
  }

  for (const root of roots) {
    const option = document.createElement("option");
    option.value = root.root_path;
    option.textContent = root.label;
    option.selected = root.root_path === activeRootPath;
    select.append(option);
  }
}

export function renderCounters(dom, workspace) {
  const counters = workspace?.counters || { total: 0, saved: 0, skipped: 0 };
  dom.metricTotal.textContent = String(counters.total || 0);
  dom.metricSaved.textContent = String(counters.saved || 0);
  dom.metricSkipped.textContent = String(counters.skipped || 0);
}

export function renderCarousel(target, workspace) {
  const cases = workspace?.cases || [];
  if (!cases.length) {
    target.innerHTML = `<div class="empty-state">Сначала загрузи таблицу и создай товары.</div>`;
    return;
  }

  target.innerHTML = cases
    .map((caseItem) => {
      const labelMeta = prefetchLabelMeta(caseItem);
      const rowLabel = `стр. ${caseItem.row_span || caseItem.row_number}`;
      const tooltip = `${rowLabel} · ${caseItem.title || "Товар"}`;
      return `
        <button class="carousel-chip ${reviewClass(caseItem)}" data-case-id="${escapeHtml(caseItem.case_id)}" type="button" title="${escapeHtml(tooltip)}">
          <span class="chip-main">
            <span class="chip-row">${escapeHtml(rowLabel)}</span>
            ${
              labelMeta
                ? `
                  <span class="chip-mark ${escapeHtml(labelMeta.className)}">
                    ${labelMeta.spinner ? `<span class="chip-mark-spinner" aria-hidden="true"></span>` : ""}
                    <span>${escapeHtml(labelMeta.text)}</span>
                  </span>
                `
                : ""
            }
          </span>
          <span class="chip-title">${escapeHtml(caseItem.title)}</span>
        </button>
      `;
    })
    .join("");
}

export function renderImages(target, currentCase) {
  const images = currentCase?.images || [];
  if (!images.length) {
    target.dataset.layout = "empty";
    target.innerHTML = `<div class="empty-state">Изображений пока нет.</div>`;
    return;
  }

  target.dataset.layout =
    images.length === 1
      ? "single"
      : images.length === 2
        ? "double"
        : images.length >= 5
          ? "dense"
          : "grid";

  target.innerHTML = images
    .map(
      (image, index) => `
        <button class="image-tile" data-image-url="${escapeHtml(image.url)}" data-image-name="${escapeHtml(image.name)}" type="button">
          <span class="image-tile-badge">${index + 1}</span>
          <img src="${escapeHtml(image.url)}" alt="${escapeHtml(image.name)}" loading="lazy" />
          <span>${escapeHtml(image.name)}</span>
        </button>
      `
    )
    .join("");
}

export function renderCaseMeta(dom, currentCase) {
  const backgroundStatusMap = {
    idle: "нет фона",
    queued: "GPT в очереди",
    running: "GPT работает",
    cancelling: "остановка...",
    completed: "GPT готов",
    cancelled: "остановлено",
    error: "ERROR",
  };
  const ocrStatus = String(currentCase?.ocr_status || "").toLowerCase();
  const backgroundStatus =
    currentCase?.background_status && currentCase.background_status !== "idle"
      ? currentCase.background_status
      : ["queued", "running", "cancelling", "completed", "cancelled", "error"].includes(ocrStatus)
        ? ocrStatus
        : "idle";
  dom.caseCaption.textContent = currentCase ? `${currentCase.case_id} · ${currentCase.title_cn || "Товар"}` : "Фото";
  dom.backgroundBadge.textContent = backgroundStatusMap[backgroundStatus] || backgroundStatus || "нет фона";
  const rawWorkStage = String(currentCase?.work_stage || "").trim();
  const visibleWorkStage = rawWorkStage && rawWorkStage !== "workbook_intake" ? rawWorkStage : "";
  dom.workStage.textContent = visibleWorkStage;
  dom.backgroundBadge.dataset.state = backgroundStatus || "idle";
  dom.workStage.dataset.state = rawWorkStage || "idle";
  dom.workStage.classList.toggle("is-hidden", !visibleWorkStage);
}

const CASE_PROGRESS_STAGES = [
  { key: "ocr", label: "OCR" },
  { key: "tnved", label: "Подбор кода" },
  { key: "semantic", label: "Семантика" },
  { key: "verification", label: "Верификация" },
  { key: "ifcg", label: "IFCG" },
  { key: "its", label: "ITS" },
  { key: "sigma", label: "Sigma" },
  { key: "customs", label: "СТП" },
];

const CASE_PROGRESS_DONE_STATUSES = new Set([
  "completed",
  "ok",
  "ready",
  "validated",
  "confirm",
  "confirmed",
  "resolved",
  "passed",
  "skipped",
]);

const CASE_PROGRESS_WARN_STATUSES = new Set([
  "mixed",
  "branch",
  "no_signal",
  "no_its_in_bot",
  "need_14_digits",
  "reply_code_mismatch",
  "unknown_response",
]);

const CASE_PROGRESS_ERROR_STATUSES = new Set([
  "error",
  "timeout",
  "http_error",
  "transport_error",
  "fetch_error",
  "parse_error",
  "cancelled",
  "worker_not_running",
  "session_invalid",
  "auth_error",
  "bot_resolve_error",
  "its_error",
  "invalid_code",
]);

function normalizeStageStatusTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized || normalized === "pending" || normalized === "unknown" || normalized === "idle") {
    return "pending";
  }
  if (CASE_PROGRESS_ERROR_STATUSES.has(normalized)) {
    return "error";
  }
  if (CASE_PROGRESS_DONE_STATUSES.has(normalized)) {
    return "done";
  }
  if (CASE_PROGRESS_WARN_STATUSES.has(normalized)) {
    return "warn";
  }
  if (["queued", "running", "processing", "cancelling", "partial"].includes(normalized)) {
    return "active";
  }
  return "pending";
}

function buildIfcgProgressStatus(stageStatuses) {
  const discoveryTone = normalizeStageStatusTone(stageStatuses?.ifcg_discovery || "");
  const verificationTone = normalizeStageStatusTone(stageStatuses?.ifcg_verification || "");
  if (discoveryTone === "error" || verificationTone === "error") {
    return "error";
  }
  if (discoveryTone === "active" || verificationTone === "active") {
    return "active";
  }
  if (verificationTone === "done" || verificationTone === "warn") {
    return verificationTone;
  }
  if (discoveryTone === "done" || discoveryTone === "warn") {
    return "active";
  }
  return "pending";
}

function isCaseProcessing(currentCase) {
  if (!currentCase) {
    return false;
  }
  const backgroundStatus = String(currentCase.background_status || "").trim().toLowerCase();
  const ocrStatus = String(currentCase.ocr_status || "").trim().toLowerCase();
  const workStatus = String(currentCase.work_status || "").trim().toLowerCase();
  return ["queued", "running", "cancelling"].includes(backgroundStatus)
    || ["queued", "running", "cancelling"].includes(ocrStatus)
    || workStatus.includes("running");
}

function buildCaseProgressStages(currentCase) {
  const stageStatuses = currentCase?.stage_statuses || {};
  return CASE_PROGRESS_STAGES.map((stage) => {
    let tone = "pending";
    if (stage.key === "ifcg") {
      tone = buildIfcgProgressStatus(stageStatuses);
    } else if (stage.key === "ocr") {
      tone = normalizeStageStatusTone(stageStatuses.ocr || currentCase?.ocr_status || "");
    } else {
      tone = normalizeStageStatusTone(stageStatuses[stage.key] || "");
    }
    return { ...stage, tone };
  });
}

function inferActiveProgressStage(currentCase, stages) {
  const workStage = String(currentCase?.work_stage || "").trim().toLowerCase();
  const backgroundStatus = String(currentCase?.background_status || "").trim().toLowerCase();
  const workStatus = String(currentCase?.work_status || "").trim().toLowerCase();

  if (backgroundStatus === "queued") {
    return "ocr";
  }
  if (workStage.includes("ocr")) {
    return "ocr";
  }
  if (workStage.includes("tnved")) {
    return "tnved";
  }
  if (workStage.includes("semantic")) {
    return "semantic";
  }
  if (workStage.includes("verification")) {
    return "verification";
  }
  if (workStage.includes("enrichment")) {
    return stages.find((stage) => ["pending", "active"].includes(stage.tone) && ["ifcg", "its", "sigma"].includes(stage.key))?.key || "ifcg";
  }
  if (workStage.includes("result")) {
    return "customs";
  }
  if (workStatus.includes("running")) {
    return stages.find((stage) => stage.tone === "pending")?.key || "ocr";
  }
  return stages.find((stage) => stage.tone === "pending")?.key || "";
}

function buildCaseProgressState(currentCase) {
  if (!isCaseProcessing(currentCase)) {
    return null;
  }

  const stages = buildCaseProgressStages(currentCase);
  const activeKey = inferActiveProgressStage(currentCase, stages);
  const visibleStages = stages.map((stage) => {
    if (stage.key === activeKey && stage.tone === "pending") {
      return { ...stage, tone: "active" };
    }
    return stage;
  });

  const completedCount = visibleStages.filter((stage) => ["done", "warn"].includes(stage.tone)).length;
  const hasActiveStage = visibleStages.some((stage) => stage.tone === "active");
  const percentRaw = ((completedCount + (hasActiveStage ? 0.58 : 0)) / visibleStages.length) * 100;
  const percent = Math.max(6, Math.min(96, Math.round(percentRaw)));
  const activeStage = visibleStages.find((stage) => stage.tone === "active") || visibleStages.find((stage) => stage.key === activeKey) || null;
  const title = currentCase?.row_number
    ? `Подбираю код по строке ${currentCase.row_number}`
    : "Подбираю код";
  const subtitle = currentCase?.title || currentCase?.title_cn || currentCase?.text_ru || currentCase?.text_cn || "Текущий товар";
  const stageLine = backgroundStatusToMessage(String(currentCase?.background_status || "").trim().toLowerCase(), activeStage?.label || "Подбор");

  return {
    title,
    subtitle,
    percent,
    stageLine,
    stages: visibleStages,
  };
}

function backgroundStatusToMessage(backgroundStatus, activeStageLabel) {
  if (backgroundStatus === "queued") {
    return "Ставлю строку в очередь на подбор";
  }
  if (backgroundStatus === "cancelling") {
    return "Останавливаю подбор по строке";
  }
  return `Сейчас идет этап: ${activeStageLabel}`;
}

export function renderCaseProgressOverlay(target, currentCase) {
  if (!target) {
    return false;
  }
  const progressState = buildCaseProgressState(currentCase);
  target.classList.toggle("is-hidden", !progressState);
  if (!progressState) {
    target.innerHTML = "";
    return false;
  }

  target.innerHTML = `
    <div class="case-progress-card">
      <div class="case-progress-kicker">Подбор ТН ВЭД</div>
      <div class="case-progress-head">
        <div>
          <div class="case-progress-title">${escapeHtml(progressState.title)}</div>
          <div class="case-progress-subtitle">${escapeHtml(progressState.subtitle)}</div>
        </div>
        <div class="case-progress-ring" aria-hidden="true" style="--case-progress-value: ${escapeHtml(String(progressState.percent))}%">
          <div class="case-progress-ring-core">
            <strong class="case-progress-ring-value">${escapeHtml(String(progressState.percent))}<span>%</span></strong>
          </div>
        </div>
      </div>
      <div class="case-progress-stage-line">${escapeHtml(progressState.stageLine)}</div>
      <div class="case-progress-stage-grid">
        ${progressState.stages
          .map(
            (stage) => `
              <div class="case-progress-stage tone-${escapeHtml(stage.tone)}">
                <span class="case-progress-stage-dot"></span>
                <span class="case-progress-stage-label">${escapeHtml(stage.label)}</span>
              </div>
            `
          )
          .join("")}
      </div>
      <div class="case-progress-note">Финальный вывод покажу автоматически, как только все этапы завершатся.</div>
    </div>
  `;
  return true;
}

export function renderBatchStatus(target, jobs = [], workspace = null) {
  if (!target) {
    return;
  }

  const relevantJob = jobs.find((job) => job.module_id === "batch_ocr");
  if (!relevantJob) {
    hideBatchBanner(target);
    return;
  }

  const terminalStatuses = new Set(["completed", "failed", "cancelled"]);
  const isTerminal = terminalStatuses.has(String(relevantJob.status || ""));
  if (!isTerminal) {
    clearBatchBannerHideTimer(target);
    delete target.dataset.hideAt;
  } else {
    const updatedAtMs = Date.parse(String(relevantJob.updated_at || ""));
    if (Number.isFinite(updatedAtMs)) {
      const hideAt = updatedAtMs + BATCH_BANNER_TERMINAL_TTL_MS;
      const remainingMs = hideAt - Date.now();
      if (remainingMs <= 0) {
        hideBatchBanner(target);
        return;
      }

      const nextHideAt = String(hideAt);
      if (target.dataset.jobId !== relevantJob.job_id || target.dataset.hideAt !== nextHideAt) {
        clearBatchBannerHideTimer(target);
        target._hideTimerId = window.setTimeout(() => {
          if (target.dataset.jobId === relevantJob.job_id && target.dataset.hideAt === nextHideAt) {
            hideBatchBanner(target);
          }
        }, remainingMs + 50);
        target.dataset.hideAt = nextHideAt;
      }
    }
  }

  const caseIds = Array.isArray(relevantJob.payload?.case_ids) ? relevantJob.payload.case_ids : [];
  const cases = Array.isArray(workspace?.cases) ? workspace.cases : [];
  const trackedCases = caseIds
    .map((caseId) => cases.find((item) => item.case_id === caseId))
    .filter(Boolean);
  const count = trackedCases.length || caseIds.length;
  const lines = String(relevantJob.output || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const completedCount = trackedCases.filter((item) => item.prefetch_status === "completed").length;
  const runningCase = trackedCases.find((item) => item.prefetch_status === "running");
  const errorCount = trackedCases.filter((item) => item.prefetch_status === "error").length;
  const queuedCount = trackedCases.filter((item) => item.prefetch_status === "queued").length;
  const cancelledCount = trackedCases.filter((item) => item.prefetch_status === "cancelled").length;
  const scopeLabel = buildBatchScopeLabel(trackedCases, count);

  let text = "";
  let useSpinner = false;
  if (relevantJob.status === "queued") {
    text = `Пакет OCR/GPT (${scopeLabel}) поставлен в очередь. В очереди: ${queuedCount || count}.`;
    useSpinner = true;
  } else if (relevantJob.status === "running") {
    const runningLabel = [runningCase?.row_number ? `стр. ${runningCase.row_number}` : "", runningCase?.title || runningCase?.case_id || ""]
      .filter(Boolean)
      .join(" · ");
    const progress = `${completedCount}/${count}`;
    const tail =
      runningLabel
        ? `Сейчас: ${runningLabel}.`
        : lines.at(-1) || "GPT выполняется.";
    text =
      `Пакет OCR/GPT (${scopeLabel}): готово ${progress}.` +
      `${queuedCount ? ` В очереди: ${queuedCount}.` : ""}` +
      `${errorCount ? ` Ошибок: ${errorCount}.` : ""}` +
      ` ${tail}`;
    useSpinner = true;
  } else if (relevantJob.status === "cancelling") {
    text = `Останавливаю пакет OCR/GPT (${scopeLabel}). Готово ${completedCount}/${count}.${queuedCount ? ` В очереди: ${queuedCount}.` : ""}`;
    useSpinner = true;
  } else if (relevantJob.status === "completed") {
    text = `Пакет OCR/GPT (${scopeLabel}) завершен. Готово ${completedCount || count}/${count}.`;
  } else if (relevantJob.status === "cancelled") {
    text = `Пакет OCR/GPT (${scopeLabel}) остановлен. Готово ${completedCount}/${count}.${cancelledCount ? ` Остановлено: ${cancelledCount}.` : ""}`;
  } else if (relevantJob.status === "failed") {
    text = `ERROR. Пакет OCR/GPT (${scopeLabel}) остановлен. Готово ${completedCount}/${count}. ${relevantJob.error || lines.at(-1) || ""}`.trim();
  } else {
    text = relevantJob.summary || "";
  }

  target.innerHTML = `${useSpinner ? `<span class="status-spinner" aria-hidden="true"></span>` : ""}<span>${escapeHtml(text)}</span>`;
  target.dataset.state = relevantJob.status || "idle";
  target.dataset.jobId = relevantJob.job_id || "";
  target.classList.remove("is-hidden");
}

export function renderAnalysis(target, currentCase, questions = [], options = {}) {
  if (!currentCase) {
    target.innerHTML = `<div class="empty-state">Открой кейс сверху. Здесь будет длинный разбор по товару.</div>`;
    return;
  }

  const titleInput = currentCase.text_cn || currentCase.title_cn || "—";
  const titleRu = currentCase.text_ru && currentCase.text_ru !== "—" ? currentCase.text_ru : "";
  const ocrText = currentCase.ocr_text || "—";
  const imageDescription = currentCase.image_description || "";
  const hasDetailedOcr = Boolean(imageDescription && imageDescription !== ocrText);
  const isExpanded = Boolean(options.expandedDetailedOcr);
  const analysisSections = Array.isArray(currentCase.analysis_sections) ? currentCase.analysis_sections : [];
  const extraSections = analysisSections
    .filter((section) => {
      const title = String(section?.title || "").trim().toLowerCase();
      return title && title !== "вход";
    })
    .map(
      (section, index) => `
        <section class="analysis-block">
          <div class="analysis-label"><span class="analysis-label-index">${escapeHtml(`${index + 4}.`)}</span><span>${escapeHtml(section.title || "Анализ")}</span></div>
          <div class="analysis-value">${multiline(section?.value || "—")}</div>
        </section>
      `
    )
    .join("");

  target.innerHTML = `
    <div class="analysis-sheet">
      <section class="analysis-block">
        <div class="analysis-label"><span class="analysis-label-index">1.</span><span>Название, что поступило</span></div>
        <div class="analysis-value analysis-value-main">${escapeHtml(titleInput)}</div>
        ${titleRu ? `<div class="analysis-value-secondary">${escapeHtml(titleRu)}</div>` : ""}
      </section>
      <section class="analysis-block">
        <div class="analysis-label"><span class="analysis-label-index">2.</span><span>Краткий OCR для оператора</span></div>
        <div class="analysis-value">${multiline(ocrText)}</div>
      </section>
      <section class="analysis-block">
        ${
          hasDetailedOcr
            ? `
              <button class="analysis-toggle" type="button" data-analysis-toggle="true">
                <span class="analysis-toggle-title"><span class="analysis-label-index">3.</span><span>Подробный OCR для проверки</span></span>
                <span class="analysis-toggle-meta">${isExpanded ? "Скрыть" : "Показать"}</span>
              </button>
              ${
                isExpanded
                  ? `<div class="analysis-value analysis-value-detailed">${multiline(imageDescription)}</div>`
                  : `<div class="analysis-hint">Здесь лежит полный фактический разбор изображения, который пойдёт дальше в следующий модуль.</div>`
              }
            `
            : `
              <div class="analysis-toggle analysis-toggle-static">
                <span class="analysis-toggle-title"><span class="analysis-label-index">3.</span><span>Подробный OCR для проверки</span></span>
                <span class="analysis-toggle-meta">Не создавался</span>
              </div>
              <div class="analysis-hint">Для этого кейса глубокий OCR не запускался: короткого OCR оказалось достаточно, поэтому отдельного полного разбора сейчас нет.</div>
            `
        }
      </section>
      ${extraSections}
    </div>
  `;
}

export function renderSourceTable(target, currentCase) {
  if (!currentCase) {
    target.innerHTML = `<div class="empty-state">Выбери кейс, чтобы увидеть исходные поля.</div>`;
    return;
  }

  const sourceTable = currentCase?.source_table;
  if (!sourceTable) {
    target.innerHTML = `<div class="empty-state">Таблица еще не подготовлена.</div>`;
    return;
  }

  const rowLabels = sourceTable.row_labels || [];
  const fields = sourceTable.fields || [];
  const metaHtml = `
    <div class="source-table-meta">
      <span class="source-table-chip">${escapeHtml(sourceTable.workbook_name || "—")}</span>
      <span class="source-table-chip">${escapeHtml(sourceTable.sheet_name || "—")}</span>
      <span class="source-table-chip">${escapeHtml(sourceTable.status || "—")}</span>
    </div>
    <div class="source-table-note">${multiline(sourceTable.note || "—")}</div>
  `;

  if (!fields.length) {
    target.innerHTML = `
      ${metaHtml}
      <div class="empty-state">Нет полей для показа.</div>
    `;
    return;
  }

  const rowCount = Math.max(
    rowLabels.length,
    ...fields.map((field) => (Array.isArray(field.values) ? field.values.length : 0))
  );
  const normalizedRowLabels = Array.from({ length: rowCount }, (_, index) => rowLabels[index] || `стр. ${index + 1}`);
  const tableRows = normalizedRowLabels.map((label, rowIndex) => ({
    label,
    values: fields.map((field) => (Array.isArray(field.values) ? field.values[rowIndex] || "—" : "—")),
  }));

  target.innerHTML = `
    ${metaHtml}
    <div class="source-table-shell">
      <table class="source-table">
        <thead>
          <tr>
            <th>Строка</th>
            ${fields.map((field) => `<th>${escapeHtml(field.label)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${tableRows
            .map(
              (row) => `
                <tr>
                  <th>${escapeHtml(row.label)}</th>
                  ${row.values.map((value) => `<td>${multiline(value)}</td>`).join("")}
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

export function renderChat(target, currentCase, chatMessages) {
  if (!currentCase) {
    target.innerHTML = `<div class="empty-state">Открой кейс, чтобы начать диалог.</div>`;
    return;
  }

  target.innerHTML = chatMessages
    .map(
      (message) => `
        <article class="chat-bubble ${message.role === "user" ? "is-user" : "is-model"}">
          <span class="chat-role">${escapeHtml(message.role === "user" ? "Ты" : "Модель")}</span>
          <p>${multiline(message.text)}</p>
        </article>
      `
    )
    .join("");
}

export function renderQuestions(target, questions, options = {}) {
  if (!questions.length) {
    target.innerHTML = "";
    return;
  }

  const expanded = Boolean(options.expanded);
  target.innerHTML = `
    <div class="question-strip ${expanded ? "is-expanded" : ""}">
      <button class="question-toggle" type="button" data-question-toggle="true">
        <span class="question-toggle-title">Уточнения</span>
        <span class="question-toggle-meta">
          <span class="question-toggle-count">${questions.length}</span>
          <span class="question-toggle-caret">${expanded ? "−" : "+"}</span>
        </span>
      </button>
      ${
        expanded
          ? `
            <div class="question-mini-list">
              ${questions
                .map(
                  (question, index) => `
                    <button class="question-mini-item" type="button" data-question-shortcut="${index + 1}" title="Подставить ${index + 1} в чат">
                      <span class="question-mini-index">${index + 1}</span>
                      <span class="question-mini-text">${escapeHtml(question)}</span>
                    </button>
                  `
                )
                .join("")}
            </div>
          `
          : `
            <div class="question-inline-badges">
              ${questions
                .map(
                  (_, index) => `
                    <button class="question-inline-badge" type="button" data-question-shortcut="${index + 1}" title="Подставить ${index + 1} в чат">
                      ${index + 1}
                    </button>
                  `
                )
                .join("")}
            </div>
          `
      }
    </div>
  `;
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function formatDecimal(value, digits = 2, prefix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${prefix}${formatNumber(value, digits)}`;
}

function formatSelectionStatus(status) {
  if (status === "resolved") {
    return "подобрано";
  }
  if (status === "ambiguous") {
    return "нужно выбрать";
  }
  if (status === "not_found") {
    return "не найдено";
  }
  if (status === "invalid") {
    return "нужно больше знаков";
  }
  if (status === "error") {
    return "ошибка";
  }
  return status || "—";
}

function formatMatchKind(kind, digitsLength) {
  if (kind === "exact") {
    return `точное совпадение по ${digitsLength} знакам`;
  }
  if (kind === "prefix") {
    return `совпадение по префиксу ${digitsLength} знаков`;
  }
  if (kind === "expanded") {
    return `совпадение по укрупненному коду ${digitsLength} знаков`;
  }
  return kind || "тип совпадения не указан";
}

function formatMatchKindCompact(kind, digitsLength) {
  if (kind === "exact") {
    return `точное совпадение по ${digitsLength} знакам`;
  }
  if (kind === "prefix") {
    return `совпадение по первым ${digitsLength} знакам`;
  }
  if (kind === "expanded") {
    return `совпадение по укрупненному коду ${digitsLength}`;
  }
  return kind || "тип не указан";
}

function formatCurrencyBadge(rate) {
  if (!rate || Number.isNaN(Number(rate.value_rub))) {
    return "";
  }
  const nominal = Number(rate.nominal || 1);
  const unitLabel = nominal > 1 ? `за ${nominal}` : "";
  return `${rate.code} ${formatDecimal(rate.value_rub, 4)} ₽${unitLabel ? ` ${unitLabel}` : ""}`;
}

function formatEcoSurchargeLabel(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return "ЭКОСБОР: —";
  }
  return `ЭКОСБОР: ${formatDecimal(numeric, 3)} $/кг`;
}

function buildEcoCodeLabels(match) {
  const labels = new Map();
  const matchedCodes = Array.isArray(match?.matched_codes) ? match.matched_codes : [];
  matchedCodes.forEach((code) => {
    const normalizedCode = String(code || "").trim();
    if (normalizedCode) {
      labels.set(normalizedCode, { code: normalizedCode, markers: new Set() });
    }
  });

  const dbEntries = Array.isArray(match?.db_entries) ? match.db_entries : [];
  dbEntries.forEach((entry) => {
    const code = String(entry?.tnved_digits || "").trim();
    if (!code) {
      return;
    }
    const bucket = labels.get(code) || { code, markers: new Set() };
    const footnotes = Array.isArray(entry?.footnotes) ? entry.footnotes : [];
    footnotes.forEach((item) => {
      const marker = String(item?.marker || "").trim();
      if (marker) {
        bucket.markers.add(marker);
      }
    });
    labels.set(code, bucket);
  });

  return Array.from(labels.values()).map((item) => ({
    code: item.code,
    label: `${item.code}${item.markers.size ? ` ${Array.from(item.markers).join(" ")}` : ""}`,
  }));
}

function renderEcoRatesHint(summaryState) {
  const rates = summaryState?.currencyRates || null;
  const usdBadge = formatCurrencyBadge(rates?.usd);
  const eurBadge = formatCurrencyBadge(rates?.eur);
  if (!usdBadge && !eurBadge && !rates?.note) {
    return "";
  }
  return `
    <div class="eco-inline-hint">
      <div class="eco-inline-hint-badges">
        ${usdBadge ? `<span class="eco-rate-badge">${escapeHtml(usdBadge)}</span>` : ""}
        ${eurBadge ? `<span class="eco-rate-badge">${escapeHtml(eurBadge)}</span>` : ""}
      </div>
      ${
        rates?.note
          ? `<div class="eco-inline-hint-note">${escapeHtml(rates.note)}${rates?.source ? ` Источник: ${escapeHtml(rates.source)}.` : ""}</div>`
          : ""
      }
    </div>
  `;
}

function renderEcoFootnotes(footnotes) {
  const rows = Array.isArray(footnotes) ? footnotes.filter((item) => item?.marker) : [];
  if (!rows.length) {
    return "";
  }
  return `
    <div class="eco-subtitle">Сноски по коду (${escapeHtml(String(rows.length))})</div>
    <div class="eco-footnote-box">
      <div class="eco-footnote-list">
        ${rows
          .map(
            (item) => `
              <div class="eco-footnote-item">
                <span class="eco-footnote-marker">${escapeHtml(item.marker || "")}</span>
                <span>${escapeHtml(item.text || "Текст сноски в книге не найден.")}</span>
              </div>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderEcoDbPreview(match) {
  const entries = Array.isArray(match?.db_entries) ? match.db_entries : [];
  if (!entries.length) {
    return "";
  }
  return `
    <div class="eco-db-action-row">
      <button
        class="eco-db-open-button"
        type="button"
        data-eco-entry-open-all="true"
        data-eco-match-key="${escapeHtml(match?.selection_key || "")}"
      >
        Раскрыть БД (${escapeHtml(String(entries.length))})
      </button>
    </div>
  `;
}

function buildStpSummary(summaryState) {
  const selectedOption = summaryState?.selectedOption || null;
  const stpValue = Number(selectedOption?.stp_value);
  const selectedEcoMatch = summaryState?.selectedEcoYearPayload?.best_match || null;
  const rawEcoSurcharge = Number(selectedEcoMatch?.surcharge_usd_per_kg);
  const ecoSurchargeValue = Number.isNaN(rawEcoSurcharge) ? null : rawEcoSurcharge;

  return {
    stpValue: Number.isNaN(stpValue) ? null : stpValue,
    ecoSurchargeValue,
    totalValue:
      Number.isNaN(stpValue) || ecoSurchargeValue === null
        ? null
        : stpValue + ecoSurchargeValue,
    selectedEcoMatch,
  };
}

function buildSigmaUrl(code) {
  const now = new Date();
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yy = String(now.getFullYear()).slice(-2);
  return `https://www.sigma-soft.ru/service/spravka/spravka.shtml?WAA_PACKAGE=PayCalc&WAA_FORM=PayCalc&SDATE=${dd}.${mm}.${yy}&SCODE=${encodeURIComponent(code)}`;
}

function buildIfcgUrl(code) {
  return `https://www.ifcg.ru/kb/tnved/${encodeURIComponent(code)}/`;
}

function buildStatusText(currentCase) {
  const stage = currentCase?.work_stage || "workbook_intake";
  if (stage === "workbook_intake") {
    return "предварительно (после подготовки кейса)";
  }
  if (stage === "01_expander") {
    return "предварительно (без semantic-подтверждения)";
  }
  return `предварительно (${escapeHtml(stage)})`;
}

function buildCriteriaText(selectedOption) {
  if (!selectedOption) {
    return "Пока нет выбранного кода для оценки.";
  }
  return selectedOption.why_alive || "Выбор требует дополнительной проверки признаков.";
}

function buildRationaleText(currentCase, selectedOption) {
  if (!currentCase || !selectedOption) {
    return "Ожидаем результаты модулей 01-05.";
  }
  const titleText = currentCase.title_ru && currentCase.title_ru !== "—"
    ? currentCase.title_ru
    : currentCase.text_cn || currentCase.title_cn || "товар";
  return `По текущему разбору товар трактуется как "${titleText}". ${selectedOption.why_alive || "Ветка пока остается рабочей до внешней проверки."}`;
}

function buildStatusFlags(selectedOption) {
  const itsStatus = selectedOption?.its && !/нет в боте/i.test(String(selectedOption.its)) ? "✅" : "—";
  const sigmaStatus = selectedOption?.posh && selectedOption.posh !== "—" ? "✅" : "—";
  return { itsStatus, sigmaStatus };
}

function formatStageStatus(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "—";
  }
  const normalized = raw.toLowerCase();
  const labels = {
    idle: "idle",
    pending: "pending",
    queued: "queued",
    running: "running",
    completed: "completed",
    partial: "partial",
    validated: "validated",
    supported: "supported",
    confirm: "confirm",
    branch: "branch",
    mixed: "mixed",
    no_signal: "no_signal",
    skipped: "skipped",
    disabled: "disabled",
    error: "error",
    not_configured: "not_configured",
    session_invalid: "session_invalid",
  };
  return labels[normalized] || raw;
}

function normalizeCodeDigits(value) {
  return String(value || "").replace(/\D/g, "");
}

function sumDigits(value) {
  return normalizeCodeDigits(value)
    .split("")
    .reduce((acc, digit) => acc + Number(digit || 0), 0);
}

function truncateText(value, limit = 180) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "—";
  }
  return normalized.length > limit ? `${normalized.slice(0, limit - 1).trimEnd()}…` : normalized;
}

function normalizeSupportKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
}

function buildProductLabel(currentCase) {
  return (
    currentCase?.text_ru ||
    currentCase?.title_ru ||
    currentCase?.text_cn ||
    currentCase?.title_cn ||
    "товар"
  );
}

function hasPositiveSignal(value) {
  if (value === true) {
    return true;
  }
  if (value === false || value === null || value === undefined) {
    return false;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    if ("is_positive" in value) {
      return Boolean(value.is_positive);
    }
    if ("has_attention" in value) {
      return Boolean(value.has_attention);
    }
    if ("active" in value) {
      return Boolean(value.active);
    }
    if ("present" in value) {
      return Boolean(value.present);
    }
    if ("value" in value) {
      return hasPositiveSignal(value.value);
    }
    return false;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (!normalized || normalized === "—" || normalized === "-" || normalized === "0") {
      return false;
    }
    if (/^(нет|none|false|n\/a|не требуется|не применя|не найден|отсутств|жд[её]т)/i.test(normalized)) {
      return false;
    }
    return true;
  }
  return false;
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null) {
      return value;
    }
  }
  return undefined;
}

function resolveEcoMarker(summaryState) {
  const ecoPacket = summaryState?.ecoPacket;
  const selectedEcoMatch = summaryState?.selectedEcoYearPayload?.best_match || null;
  if (selectedEcoMatch || summaryState?.selectedOption?.eco?.startsWith("+")) {
    return { tone: "good", title: "Есть eco-сигнал и доплата к СТП" };
  }
  if (summaryState?.selectedEcoYearPayload?.status === "ambiguous") {
    return { tone: "warn", title: "По коду найдено несколько eco-групп, смотри сводку внизу" };
  }
  if (summaryState?.selectedEcoYearPayload?.status === "resolved" || ecoPacket?.status === "resolved") {
    return { tone: "good", title: "Eco-группа подобрана" };
  }
  return { tone: "neutral", title: "По коду eco-сигнал пока не подтвержден" };
}

function buildSboryMarkers(summaryState) {
  const selectedOption = summaryState?.selectedOption || null;
  const sigmaFlags =
    selectedOption?.sigma_flags && typeof selectedOption.sigma_flags === "object" ? selectedOption.sigma_flags : {};
  const sigmaSignals =
    selectedOption?.sigma_signals && typeof selectedOption.sigma_signals === "object" ? selectedOption.sigma_signals : {};
  const ecoMeta = resolveEcoMarker(summaryState);
  const markers = [];

  const customsFeeSignal = firstDefined(
    sigmaFlags.customs_fee,
    sigmaSignals.customs_fee,
    selectedOption?.customs_fee_signal,
    selectedOption?.customs_fee
  );
  if (hasPositiveSignal(customsFeeSignal)) {
    markers.push({
      emoji: "🧾",
      label: "Там. сбор",
      tone: "good",
      title: "Фиксированный таможенный сбор / PP1637 local",
    });
  }

  const protectiveSignal = firstDefined(
    sigmaFlags.protective,
    sigmaSignals.protective,
    selectedOption?.protective_signal,
    selectedOption?.protective_measures
  );
  if (hasPositiveSignal(protectiveSignal)) {
    markers.push({
      emoji: "🛡️",
      label: "Доп. меры",
      tone: "warn",
      title: "Антидемпинг / спецпошлина / компенсационные меры из Sigma",
    });
  }

  const exciseSignal = firstDefined(
    sigmaFlags.excise,
    sigmaSignals.excise,
    selectedOption?.excise_signal,
    selectedOption?.excise
  );
  if (hasPositiveSignal(exciseSignal)) {
    markers.push({
      emoji: "💰",
      label: "Акциз",
      tone: "warn",
      title: "Акциз из Sigma",
    });
  }

  const honestSignSignal = firstDefined(
    sigmaFlags.mandatory_marking,
    sigmaSignals.mandatory_marking,
    selectedOption?.chz_signal,
    selectedOption?.mandatory_marking
  );
  if (hasPositiveSignal(honestSignSignal)) {
    markers.push({
      emoji: "🏷️",
      label: "Честный знак",
      tone: "warn",
      title: "Честный знак / обязательная маркировка из Sigma",
    });
  }

  const ecoSignal = firstDefined(
    sigmaFlags.eco,
    sigmaSignals.eco,
    selectedOption?.eco_signal,
    selectedOption?.sigma_eco_signal
  );
  if (hasPositiveSignal(ecoSignal) || ecoMeta.tone === "good" || ecoMeta.tone === "warn") {
    markers.push({
      emoji: "♻️",
      label: "Эко",
      tone: ecoMeta.tone === "neutral" ? "good" : ecoMeta.tone,
      title: ecoMeta.title,
    });
  }

  return markers;
}

function renderSboryMarkers(markers) {
  if (!markers.length) {
    return "";
  }
  return `
    <div class="output-sbory-markers">
      ${markers
        .map(
          (marker) => `
            <div class="sbory-marker tone-${escapeHtml(marker.tone)}" title="${escapeHtml(marker.title)}">
              <span class="sbory-marker-icon">${escapeHtml(marker.emoji)}</span>
              <strong>${escapeHtml(marker.label)}</strong>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderInlineMetrics(selectedOption, summary, summaryState) {
  const stpSummary = buildStpSummary(summaryState);
  const hasEcoTotal = stpSummary.totalValue !== null;
  const stpLabel = hasEcoTotal ? "СТП + ЭКО" : "СТП";
  const stpValue = hasEcoTotal
    ? formatDecimal(stpSummary.totalValue, 2)
    : selectedOption?.stp || summary?.stp || "руками";
  const stpFormula = hasEcoTotal
    ? `${formatDecimal(stpSummary.stpValue, 2)} + ${formatDecimal(stpSummary.ecoSurchargeValue, 2)} = ${formatDecimal(stpSummary.totalValue, 2)}`
    : "";

  const cells = [
    { label: "ИТС", value: selectedOption?.its || summary?.its || "—" },
    { label: "ПОШ", value: selectedOption?.posh || summary?.posh || "—" },
    { label: "НДС", value: selectedOption?.nds || summary?.nds || "—" },
    {
      label: stpLabel,
      value: stpValue,
      detail: stpFormula,
      className: hasEcoTotal ? "has-formula" : "",
    },
  ];
  return `
    <div class="output-code-metric-line">
      ${cells
        .map(
          (cell) => `
            <div class="output-code-metric ${escapeHtml(cell.className || "")}">
              <span>${escapeHtml(cell.label)}</span>
              <strong>${escapeHtml(cell.value)}</strong>
              ${cell.detail ? `<em>${escapeHtml(cell.detail)}</em>` : ""}
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function buildIfcgSummaryMap(currentCase) {
  const panel = currentCase?.ifcg_panel || null;
  const rows = [];
  if (panel?.selected_summary) {
    rows.push(panel.selected_summary);
  }
  if (Array.isArray(panel?.candidate_summaries)) {
    rows.push(...panel.candidate_summaries);
  }
  const map = new Map();
  rows.forEach((item) => {
    const code = String(item?.code || "");
    if (code) {
      map.set(code, item);
    }
  });
  return map;
}

function renderIfcgInlineLine(summary) {
  if (!summary) {
    return `<div class="output-body is-small is-muted">IFCG: сигнала нет</div>`;
  }
  return `
    <div class="output-body is-small">${escapeHtml(summary.short_line || "IFCG: сигнала нет")}</div>
    ${summary.verify_line ? `<div class="output-body is-small is-muted">${escapeHtml(summary.verify_line)}</div>` : ""}
  `;
}

function renderAlternatives(alternatives, currentCase) {
  if (!alternatives.length) {
    return `<div class="output-body is-muted">Явных альтернатив пока нет.</div>`;
  }
  const ifcgSummaryMap = buildIfcgSummaryMap(currentCase);

  return `
    <div class="output-alternatives">
      ${alternatives
        .map(
          (option) => `
            <article class="output-alt-card">
              <div class="output-alt-head">
                <button class="output-code-button" type="button" data-code-option-key="${escapeHtml(option.option_key)}">${escapeHtml(option.code)}</button>
                <span class="output-confidence">(${escapeHtml(option.confidence_percent)}%)</span>
              </div>
              <div class="output-alt-metrics">
                ИТС=${escapeHtml(option.its)} | ПОШ=${escapeHtml(option.posh)} | ЭКО=${escapeHtml(option.eco)} | СТП=${escapeHtml(option.stp)}
              </div>
              ${renderIfcgInlineLine(ifcgSummaryMap.get(String(option.code || "")))}
              <div class="output-body is-small">${escapeHtml(option.why_alive || "Нужна дополнительная проверка отличающего признака.")}</div>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderEcoLookup(summaryState) {
  const ecoPacket = summaryState?.ecoPacket;
  const ecoYearPayload = summaryState?.selectedEcoYearPayload;
  const selectedEcoYear = Number(summaryState?.selectedEcoYear || 2026);
  const selectedOption = summaryState?.selectedOption || null;
  const isEcoExpanded = summaryState?.isEcoExpanded !== false;

  if (!selectedOption) {
    return `
      <section class="output-section">
        <div class="output-term">Экосбор:</div>
        <div class="output-body is-muted">Появится после того, как по товару будет выбран или предложен код.</div>
      </section>
    `;
  }

  if (!ecoPacket || !ecoYearPayload) {
    return `
      <section class="output-section">
        <div class="output-term">Экосбор:</div>
        <div class="output-body is-muted">Для выбранного кода eco-пакет пока не подготовлен.</div>
      </section>
    `;
  }
  const supportedYears = Array.isArray(ecoPacket.supported_years) ? ecoPacket.supported_years : [];
  const matches = Array.isArray(ecoYearPayload.matches) ? ecoYearPayload.matches : [];
  const bestMatch = ecoYearPayload.best_match || null;
  const hasMatches = Boolean(matches.length);

  return `
    <section class="output-section">
      <div class="output-headline">
        <div class="output-term">Экосбор:</div>
        <div class="eco-head-actions">
          <span class="output-inline-status">${escapeHtml(formatSelectionStatus(ecoYearPayload.status))}</span>
          <button class="eco-toggle-button" type="button" data-eco-toggle="${isEcoExpanded ? "collapse" : "expand"}">
            ${isEcoExpanded ? "Скрыть" : "Показать"}
          </button>
        </div>
      </div>
      ${renderEcoRatesHint(summaryState)}
      <div class="output-body">${escapeHtml(ecoYearPayload.note || "—")}</div>
      ${
        isEcoExpanded
          ? `
            ${
              supportedYears.length
                ? `
                  <div class="eco-year-switch">
                    ${supportedYears
                      .map(
                        (year) => `
                          <button class="eco-year-button ${Number(year) === selectedEcoYear ? "is-active" : ""}" type="button" data-eco-year="${escapeHtml(year)}">${escapeHtml(String(year))}</button>
                        `
                      )
                      .join("")}
                  </div>
                `
                : ""
            }
            ${
              hasMatches
                ? `
                  <div class="eco-match-list eco-match-list-static">
                    ${matches
                      .map(
                        (match) => `
                          <article class="eco-match-card ${bestMatch && bestMatch.selection_key === match.selection_key ? "is-selected" : ""}">
                            <div class="eco-match-head">
                              <div>
                                <div class="eco-match-title">${escapeHtml(match.eco_group_name)}</div>
                                <div class="eco-match-meta">
                                  Группа ${escapeHtml(match.eco_group_code)} · ${escapeHtml(formatMatchKindCompact(match.match_kind, match.matched_digits_length))} · строки ${escapeHtml(match.source_rows.join(", "))}
                                </div>
                              </div>
                            </div>
                            <div class="eco-match-eco-line">${escapeHtml(formatEcoSurchargeLabel(match.surcharge_usd_per_kg))}</div>
                            <div class="eco-subtitle">Наименования в базе экосбора (${escapeHtml(String(match.examples?.length || 0))})</div>
                            ${
                              match.examples?.length
                                ? `
                                  <div class="eco-example-box">
                                    <ul class="eco-example-list">
                                      ${match.examples.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                                    </ul>
                                  </div>
                                `
                                : `<div class="output-body is-small">По этой группе названия в книге не найдены.</div>`
                            }
                            ${
                              match.matched_codes?.length
                                ? `
                                  <div class="eco-subtitle">Коды из базы (${escapeHtml(String(match.matched_codes.length))})</div>
                                  <div class="eco-code-box">
                                    <div class="eco-code-list">${buildEcoCodeLabels(match).map((item) => `<span>${escapeHtml(item.label)}</span>`).join("")}</div>
                                  </div>
                                `
                                : ""
                            }
                            ${renderEcoFootnotes(match.footnotes)}
                            ${renderEcoDbPreview(match)}
                          </article>
                        `
                      )
                      .join("")}
                  </div>
                `
                : `<div class="output-body is-muted">В базе экосбора совпадений пока нет.</div>`
            }
          `
          : ""
      }
    </section>
  `;
}

function formatTnvedVbdStatus(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "confirmed") {
    return "подтвержден";
  }
  if (normalized === "needs_review") {
    return "нужна проверка";
  }
  if (normalized === "no_signal") {
    return "слабый сигнал";
  }
  if (normalized === "no_hits") {
    return "нет совпадений";
  }
  if (normalized === "unavailable") {
    return "база пуста";
  }
  if (normalized === "pending") {
    return "pending";
  }
  if (normalized === "skipped") {
    return "skipped";
  }
  if (normalized === "error") {
    return "error";
  }
  return normalized || "pending";
}

function renderTnvedVbdHits(items, title) {
  const hits = Array.isArray(items) ? items : [];
  if (!hits.length) {
    return "";
  }
  return `
    <div class="tnved-vbd-group">
      <div class="tnved-vbd-subtitle">${escapeHtml(title)}</div>
      <div class="tnved-vbd-hit-list">
        ${hits
          .map(
            (hit) => `
              <article class="tnved-vbd-hit">
                <div class="tnved-vbd-hit-head">
                  <span class="tnved-vbd-hit-path">${escapeHtml(hit.relative_path || hit.source_path || "document")}</span>
                  <span class="tnved-vbd-hit-score">релевантность ${escapeHtml(formatDecimal(hit.score, 2))}</span>
                </div>
                ${
                  Array.isArray(hit.mentioned_codes) && hit.mentioned_codes.length
                    ? `<div class="tnved-vbd-hit-codes">${hit.mentioned_codes.map((code) => `<span>${escapeHtml(code)}</span>`).join("")}</div>`
                    : ""
                }
                <div class="output-body is-small">${escapeHtml(hit.section_context || String(hit.text || "").slice(0, 200) || "—")}</div>
                <div class="output-body is-small is-muted">${escapeHtml(String(hit.text || "").slice(0, 320) || "—")}</div>
              </article>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderTnvedVbdWindow(currentCase) {
  const panel = currentCase?.tnved_vbd;
  if (!panel) {
    return `
      <section class="output-section tnved-vbd-panel">
        <div class="output-term">ТН ВЭД / VBD:</div>
        <div class="output-body is-muted">Появится после финального выбора кода.</div>
      </section>
    `;
  }

  const facts = Array.isArray(panel.product_facts) ? panel.product_facts : [];
  const alternatives = Array.isArray(panel.alternative_codes) ? panel.alternative_codes : [];
  const referenceHits = Array.isArray(panel.reference_hits) ? panel.reference_hits.slice(0, 3) : [];
  const exampleHits = Array.isArray(panel.example_hits) ? panel.example_hits.slice(0, 2) : [];
  const statusText = formatTnvedVbdStatus(panel.verification_status || panel.status);

  return `
    <section class="output-section tnved-vbd-panel">
      <div class="output-headline">
        <div class="output-term">ТН ВЭД / VBD:</div>
        <span class="output-inline-status">${escapeHtml(statusText)}</span>
      </div>
      <div class="output-body">${escapeHtml(panel.summary || panel.note || "Сигнал еще не сформирован.")}</div>
      ${
        panel.note && panel.note !== panel.summary
          ? `<div class="output-body is-small is-muted">${escapeHtml(panel.note)}</div>`
          : ""
      }
      ${
        facts.length
          ? `
            <div class="tnved-vbd-group">
              <div class="tnved-vbd-subtitle">Факты по товару</div>
              <div class="tnved-vbd-facts">
                ${facts.map((item) => `<span class="tnved-vbd-fact">${escapeHtml(item)}</span>`).join("")}
              </div>
            </div>
          `
          : ""
      }
      ${
        alternatives.length
          ? `
            <div class="tnved-vbd-group">
              <div class="tnved-vbd-subtitle">Альтернативные коды</div>
              <div class="tnved-vbd-facts">
                ${alternatives.map((item) => `<span class="tnved-vbd-fact is-code">${escapeHtml(item)}</span>`).join("")}
              </div>
            </div>
          `
          : ""
      }
      ${renderTnvedVbdHits(referenceHits, "Документы")}
      ${renderTnvedVbdHits(exampleHits, "Примеры")}
    </section>
  `;
}

export function renderOutputStatusLine(target, currentCase, summaryState = {}) {
  if (!target) {
    return;
  }
  if (!currentCase) {
    target.innerHTML = "";
    return;
  }
  const stageStatuses = currentCase?.stage_statuses || {};
  const semanticStatus = String(stageStatuses.semantic || "").toLowerCase();
  const routeLabel = semanticStatus && semanticStatus !== "pending"
    ? "OCR deep + semantic"
    : "OCR deep + no-semantic";
  const iconForStatus = (value) => {
    const status = String(value || "").toLowerCase();
    if (["completed", "ready", "ok", "passed", "validated", "confirm"].includes(status)) {
      return "✅";
    }
    if (["running", "queued", "processing", "partial"].includes(status)) {
      return "⏳";
    }
    return "❌";
  };
  target.innerHTML = `
    <span class="output-status-line"><span class="output-status-label">РО:</span> <span class="output-status-value">${escapeHtml(routeLabel)}</span></span>
    <span class="output-status-line"><span class="output-status-label">ИТС БОТ:</span> <span class="output-status-value">${iconForStatus(stageStatuses.its || "")}</span></span>
    <span class="output-status-line"><span class="output-status-label">SIGMA-SOFT:</span> <span class="output-status-value">${iconForStatus(stageStatuses.sigma || "")}</span></span>
  `;
}

function renderIfcgPanel(currentCase) {
  const panel = currentCase?.ifcg_panel;
  if (!panel) {
    return "";
  }
  const queries = Array.isArray(panel.queries) ? panel.queries : [];
  const topCodes = Array.isArray(panel.top_codes) ? panel.top_codes : [];
  const shownQueries = queries.slice(0, 5);
  const hiddenCount = Number(panel.hidden_queries || Math.max(0, queries.length - shownQueries.length));
  const formatGroups = (groups) =>
    (Array.isArray(groups) ? groups : [])
      .map((item) => `${escapeHtml(item.code)} — ${escapeHtml(String(item.record_count || 0))} записей, ${escapeHtml(String(item.share_percent || 0))}%`)
      .join("; ");
  const topCodesSummary = topCodes
    .slice(0, 3)
    .map((item) => {
      const itsPart =
        item.its_value !== null && item.its_value !== undefined
          ? ` | ИТС=${escapeHtml(String(item.its_value))}`
          : item.its_date_text
            ? ` | ИТС=${escapeHtml(item.its_date_text)}`
            : "";
      return `${escapeHtml(item.code)} — ${escapeHtml(String(item.records || 0))} записей, ${escapeHtml(String(item.share_percent || 0))}%${itsPart}`;
    })
    .join("<br />");

  return `
    <section class="output-section output-ifcg-panel">
      <div class="output-term">IFCG review</div>
      <div class="output-body">${escapeHtml(panel.review_headline || panel.summary || "IFCG: сигнала нет")}</div>
      ${
        panel.selected_code
          ? `<div class="output-body is-small"><strong>Текущий выбор:</strong> ${escapeHtml(panel.selected_code)}${panel.strongest_code && panel.strongest_code !== panel.selected_code ? ` · сильнейший код по практике: ${escapeHtml(panel.strongest_code)}` : ""}</div>`
          : ""
      }
      ${
        shownQueries.length
          ? `
            <div class="output-term">Запросы IFCG:</div>
            <ol class="ifcg-review-list">
              ${shownQueries
                .map(
                  (item) => `
                    <li class="ifcg-review-item">
                      <div class="ifcg-review-head">
                        <span class="ifcg-review-index">${escapeHtml(String(item.index || ""))}.</span>
                        ${
                          item.url
                            ? `<a class="ifcg-review-link" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.text)}</a>`
                            : `<span class="ifcg-review-link is-static">${escapeHtml(item.text)}</span>`
                        }
                      </div>
                      <div class="output-body is-small">${formatGroups(item.groups) || "Устойчивого сигнала не дал."}</div>
                      ${
                        Array.isArray(item.focused) && item.focused.length
                          ? `<div class="output-body is-small">${item.focused.map((row) => `Группа ${escapeHtml(row.group_filter || "—")}: ${formatGroups(row.codes)}`).join("<br />")}</div>`
                          : ""
                      }
                    </li>
                  `
                )
                .join("")}
            </ol>
            ${hiddenCount ? `<div class="output-body is-small">Остальные запросы: ${hiddenCount} шт. скрыты.</div>` : ""}
          `
          : ""
      }
      ${
        topCodesSummary
          ? `
            <div class="output-term">Сводка по кодам IFCG:</div>
            <div class="output-body is-small">${topCodesSummary}</div>
          `
          : ""
      }
      ${panel.rerun_recommended ? `<div class="output-body">IFCG рекомендует повторный пересмотр основного подбора.</div>` : ""}
    </section>
  `;
}

export function renderSummary(target, currentCase, summaryState = {}) {
  if (!currentCase) {
    target.innerHTML = `<div class="empty-state">Открой кейс, чтобы увидеть будущий вывод модели.</div>`;
    return;
  }

  const selectedOption = summaryState.selectedOption || null;
  const alternatives = summaryState.alternatives || [];
  const summary = currentCase.summary || {};
  const selectedCode = selectedOption?.code || summary.tnved || "—";
  const confidence = selectedOption?.confidence_percent || 0;
  const sboryMarkers = buildSboryMarkers(summaryState);
  const ifcgSummaryMap = buildIfcgSummaryMap(currentCase);
  const selectedIfcgSummary = ifcgSummaryMap.get(String(selectedCode || ""));
  const codeHeadline =
    selectedCode !== "—"
      ? `
        <button class="output-code-button is-main" type="button" data-code-option-key="${escapeHtml(selectedOption?.option_key || "")}">
          ${escapeHtml(selectedCode)}
        </button>
      `
      : `<span class="output-code-placeholder">код пока не выбран</span>`;

  target.innerHTML = `
    <div class="output-canvas-body">
      <div class="output-report">
        <section class="output-section output-code-section">
          <div class="output-line-wrap output-code-headline">
            <span class="output-term">ТНВЭД:</span>
            ${codeHeadline}
            ${
              selectedCode !== "—"
                ? `
                  <span class="output-links">
                    (<a href="${escapeHtml(buildSigmaUrl(selectedCode))}" target="_blank" rel="noreferrer">sigm</a>
                    /
                    <a href="${escapeHtml(buildIfcgUrl(selectedCode))}" target="_blank" rel="noreferrer">icfg</a>)
                  </span>
                  <span class="output-confidence">(${escapeHtml(confidence)}%)</span>
                `
                : ""
            }
          </div>
          ${
            selectedCode !== "—"
              ? `
                <div class="output-code-stickerset">
                  ${renderInlineMetrics(selectedOption, summary, summaryState)}
                  ${renderSboryMarkers(sboryMarkers)}
                </div>
                ${renderIfcgInlineLine(selectedIfcgSummary)}
              `
              : ""
          }
        </section>

        <section class="output-section">
          <div class="output-term">Описание ТНВЭД:</div>
          <div class="output-body">${escapeHtml(selectedOption?.title || summary.declaration_description || "—")}</div>
        </section>

        <section class="output-section">
          <div class="output-term">Критерии выбора:</div>
          <div class="output-body">${escapeHtml(buildCriteriaText(selectedOption))}</div>
        </section>

        <section class="output-section">
          <div class="output-term">Обоснование:</div>
          <div class="output-body">${escapeHtml(buildRationaleText(currentCase, selectedOption))}</div>
        </section>

        <section class="output-section">
          <div class="output-term">Альтернативы:</div>
          ${renderAlternatives(alternatives, currentCase)}
        </section>

        ${renderEcoLookup(summaryState)}
        ${renderTnvedVbdWindow(currentCase)}
        ${renderIfcgPanel(currentCase)}
      </div>
    </div>
  `;
}

export function renderModule0Status(target, inspectPayload, jobs, uploadState = null) {
  const lastJob = jobs.find((job) => job.module_id === "workbook_intake");
  if (uploadState?.isActive) {
    const percent = Number.isFinite(uploadState.percent) ? Math.max(0, Math.min(100, Math.round(uploadState.percent))) : 0;
    const totalMb =
      Number.isFinite(uploadState.total) && uploadState.total > 0
        ? ` из ${formatFileSize(uploadState.total)}`
        : "";
    target.textContent = `Загрузка файла ${uploadState.fileName || "Excel"} на сервер: ${percent}% (${formatFileSize(uploadState.loaded || 0)}${totalMb}).`;
    return;
  }
  let inspectLine = "Жду Excel-файл для проверки.";
  if (inspectPayload) {
    const firstError = Array.isArray(inspectPayload.validation_errors) ? inspectPayload.validation_errors[0] : "";
    inspectLine = inspectPayload.is_workbook_compatible
      ? `${inspectPayload.selected_sheet} · ${inspectPayload.total_data_rows} строк · таблица готова к созданию товаров`
      : `${inspectPayload.selected_sheet} · ${inspectPayload.total_data_rows} строк · ошибка: ${firstError || "таблица не прошла проверку"}`;
  }
  const jobLine = lastJob ? `Последняя подготовка: ${lastJob.status}` : "Подготовка еще не запускалась.";
  target.textContent = `${inspectLine} ${jobLine}`;
}

function formatFileSize(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 MB";
  }
  const megabytes = bytes / (1024 * 1024);
  if (megabytes >= 100) {
    return `${Math.round(megabytes)} MB`;
  }
  if (megabytes >= 10) {
    return `${megabytes.toFixed(1)} MB`;
  }
  return `${megabytes.toFixed(2)} MB`;
}
