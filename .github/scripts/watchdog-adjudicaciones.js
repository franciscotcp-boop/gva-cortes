"use strict";

const QUEUE_STATUSES = new Set(["queued", "requested", "waiting", "pending"]);
const ACTIVE_STATUSES = new Set([...QUEUE_STATUSES, "in_progress"]);
const FAILURE_CONCLUSIONS = new Set(["failure", "timed_out", "startup_failure"]);
const FAILURE_ISSUE_TITLE = "[AdjudicApp] Recuperacion automatica fallida";

function envBoolean(value) {
  return /^(1|true|yes|si)$/i.test(String(value || ""));
}

function positiveNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function ageMinutes(value, now = new Date()) {
  const timestamp = Date.parse(String(value || ""));
  if (!Number.isFinite(timestamp)) return Number.POSITIVE_INFINITY;
  return Math.max(0, (now.getTime() - timestamp) / 60000);
}

function madridCalendar(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Madrid",
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "numeric",
    hourCycle: "h23",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return {
    month: Number(values.month),
    day: Number(values.day),
    weekday: values.weekday,
    hour: Number(values.hour),
  };
}

function calendarModes(now = new Date()) {
  const { month, day, weekday } = madridCalendar(now);
  const modes = [];
  if ((month === 7 || month === 8) && weekday !== "Sun") modes.push("inicio");
  if (month !== 7 && month !== 8 && (weekday === "Tue" || weekday === "Thu")) modes.push("curso");
  if (month === 6 || month === 7) modes.push("posiciones");
  if (month !== 8 && weekday === "Fri") modes.push("acreditaciones");
  const offersInSeason = (month >= 9 || month <= 6) || (month === 7 && day === 1);
  if (offersInSeason && (weekday === "Mon" || weekday === "Wed")) modes.push("puestos");
  return modes;
}

function shouldMonitor(now = new Date(), eventName = "schedule") {
  if (eventName !== "schedule") return true;
  const { hour } = madridCalendar(now);
  return calendarModes(now).length > 0 && hour >= 9 && hour <= 22;
}

function runAgeMinutes(run, now = new Date()) {
  const reference = run.status === "in_progress"
    ? (run.run_started_at || run.created_at)
    : run.created_at;
  return ageMinutes(reference, now);
}

function staleRunReason(run, now = new Date(), staleMinutes = 30) {
  const age = runAgeMinutes(run, now);
  if (QUEUE_STATUSES.has(run.status) && age > staleMinutes) {
    return `en cola durante ${Math.floor(age)} minutos`;
  }
  if (run.status === "in_progress" && age > staleMinutes) {
    return `en ejecucion durante ${Math.floor(age)} minutos`;
  }
  return "";
}

function generatedAtHealth(value, now = new Date(), staleMinutes = 30) {
  const age = ageMinutes(value, now);
  return {
    value: value || null,
    ageMinutes: age,
    stale: !Number.isFinite(age) || age > staleMinutes,
  };
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

function sortNewest(runs) {
  return [...runs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

function consecutiveFailureRuns(runs) {
  const failures = [];
  for (const run of sortNewest(runs)) {
    if (run.status !== "completed") continue;
    if (run.conclusion === "success") break;
    if (FAILURE_CONCLUSIONS.has(run.conclusion)) failures.push(run);
  }
  return failures;
}

function runDescription(run, now = new Date()) {
  if (!run) return "No localizada";
  return `#${run.run_number || run.id} (${run.status}, ${Math.floor(runAgeMinutes(run, now))} min) ${run.html_url || ""}`.trim();
}

function madridTimestamp(now = new Date()) {
  return new Intl.DateTimeFormat("es-ES", {
    timeZone: "Europe/Madrid",
    dateStyle: "full",
    timeStyle: "long",
  }).format(now);
}

function buildIncidentReport({
  now,
  staleRuns,
  cancellationResults,
  generatedBefore,
  generatedAfter,
  failedRuns = [],
  recoveryRun,
  recoveryStarted,
  recoverySucceeded,
  recoveryMessage,
}) {
  const blocked = staleRuns.length
    ? staleRuns.map(run => `- ${runDescription(run, now)}: ${staleRunReason(run, now)}`).join("\n")
    : "- No habia una ejecucion bloqueada; se detectaron fallos en una comprobacion reciente.";
  const cancellations = cancellationResults.length
    ? cancellationResults.map(item => `- #${item.run.run_number || item.run.id}: ${item.cancelled ? "cancelada automaticamente" : `no se pudo cancelar (${item.error})`}`).join("\n")
    : "- No fue necesaria ninguna cancelacion.";
  const failures = failedRuns.length
    ? failedRuns.slice(0, 10).map(run => `- ${runDescription(run, now)}; resultado ${run.conclusion}`).join("\n")
    : "- No se detectaron fallos consecutivos.";

  return [
    "@franciscotcp-boop",
    "",
    "El vigilante automatico de AdjudicApp ha intervenido.",
    "",
    `**Fecha:** ${madridTimestamp(now)}`,
    `**Estado final:** ${recoverySucceeded ? "RECUPERACION CORRECTA" : "RECUPERACION FALLIDA"}`,
    "",
    "### Ejecucion bloqueada",
    blocked,
    "",
    "### Cancelacion automatica",
    cancellations,
    "",
    "### Fallos consecutivos",
    failures,
    "",
    "### Nueva ejecucion",
    recoveryStarted
      ? `- Se lanzo o reutilizo una nueva comprobacion: ${runDescription(recoveryRun, new Date())}`
      : "- No se pudo lanzar una nueva comprobacion.",
    "",
    "### Comprobacion del JSON",
    `- generated_at anterior: ${generatedBefore.value || "ausente o no valido"}`,
    `- generated_at posterior: ${generatedAfter.value || "ausente o no valido"}`,
    "",
    `### Resultado\n${recoveryMessage}`,
    "",
    "Este informe ha sido generado automaticamente. El vigilante no tiene permiso para modificar la web, la app ni el contenido del JSON.",
  ].join("\n");
}

async function readJsonMetadata(github, owner, repo, path) {
  const response = await github.rest.repos.getContent({ owner, repo, path });
  if (Array.isArray(response.data)) throw new Error(`${path} no es un archivo`);

  let encoded = response.data.content || "";
  if (!encoded && response.data.sha) {
    const blob = await github.rest.git.getBlob({ owner, repo, file_sha: response.data.sha });
    encoded = blob.data.content || "";
  }
  if (!encoded) throw new Error(`No se pudo leer ${path}`);

  const text = Buffer.from(encoded.replace(/\s/g, ""), "base64").toString("utf8");
  const data = JSON.parse(text);
  return {
    generatedAt: data.generated_at || null,
    schemaVersion: data.schema_version || null,
    schoolYear: data.cuts && data.cuts.inicio ? data.cuts.inicio.school_year || null : null,
  };
}

async function listPrimaryRuns(github, owner, repo, workflowId) {
  const response = await github.rest.actions.listWorkflowRuns({
    owner,
    repo,
    workflow_id: workflowId,
    per_page: 100,
  });
  return response.data.workflow_runs || [];
}

async function waitUntilCompleted(github, owner, repo, runId, waitMinutes) {
  const deadline = Date.now() + waitMinutes * 60000;
  let run = null;
  while (Date.now() < deadline) {
    const response = await github.rest.actions.getWorkflowRun({ owner, repo, run_id: runId });
    run = response.data;
    if (run.status === "completed") return run;
    await sleep(15000);
  }
  return run;
}

async function findNewDispatch(github, owner, repo, workflowId, dispatchedAt) {
  const earliest = dispatchedAt.getTime() - 10000;
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    const runs = await listPrimaryRuns(github, owner, repo, workflowId);
    const match = sortNewest(runs).find(run =>
      run.event === "workflow_dispatch" &&
      Date.parse(run.created_at) >= earliest
    );
    if (match) return match;
    await sleep(5000);
  }
  return null;
}

async function findOpenFailureIssue(github, owner, repo) {
  const openIssues = await github.rest.issues.listForRepo({ owner, repo, state: "open", per_page: 100 });
  return (openIssues.data || []).find(issue => issue.title === FAILURE_ISSUE_TITLE) || null;
}

async function resolveRecoveredIncident(github, owner, repo, generatedAt, now = new Date()) {
  const existingFailure = await findOpenFailureIssue(github, owner, repo);
  if (!existingFailure) return null;

  const body = [
    `@${owner}`,
    "",
    "**RECUPERACION CONFIRMADA**",
    "",
    "Una comprobacion posterior confirma que el proceso principal ha vuelto a terminar correctamente.",
    `- Fecha: ${madridTimestamp(now)}`,
    `- generated_at: ${generatedAt || "no disponible"}`,
    "",
    "La incidencia se cierra automaticamente.",
  ].join("\n");

  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: existingFailure.number,
    body,
  });
  await github.rest.issues.update({
    owner,
    repo,
    issue_number: existingFailure.number,
    state: "closed",
    state_reason: "completed",
  });
  return existingFailure.html_url;
}

async function notifyIncident(github, owner, repo, success, body) {
  const existingFailure = await findOpenFailureIssue(github, owner, repo);

  if (existingFailure) {
    await github.rest.issues.createComment({ owner, repo, issue_number: existingFailure.number, body });
    if (success) {
      await github.rest.issues.update({
        owner,
        repo,
        issue_number: existingFailure.number,
        state: "closed",
        state_reason: "completed",
      });
    }
    return existingFailure.html_url;
  }

  const title = success
    ? "[AdjudicApp] Recuperacion automatica completada"
    : FAILURE_ISSUE_TITLE;
  const created = await github.rest.issues.create({
    owner,
    repo,
    title,
    body,
    assignees: [owner],
  });
  if (success) {
    await github.rest.issues.update({
      owner,
      repo,
      issue_number: created.data.number,
      state: "closed",
      state_reason: "completed",
    });
  }
  return created.data.html_url;
}

async function sendTestAlert(github, owner, repo) {
  const body = [
    `@${owner}`,
    "",
    "Esta es una prueba del canal de correo del vigilante de AdjudicApp.",
    "No se ha cancelado ni relanzado ninguna ejecucion y no se ha modificado el JSON.",
  ].join("\n");
  const created = await github.rest.issues.create({
    owner,
    repo,
    title: "[AdjudicApp] Prueba del correo del vigilante",
    body,
    assignees: [owner],
  });
  await github.rest.issues.update({
    owner,
    repo,
    issue_number: created.data.number,
    state: "closed",
    state_reason: "completed",
  });
  return created.data.html_url;
}

async function runWatchdog({ github, context, core, now = new Date(), sleepFn = sleep }) {
  const { owner, repo } = context.repo;
  const workflowId = process.env.PRIMARY_WORKFLOW || "update-adjudicaciones.yml";
  const dataPath = process.env.DATA_PATH || "data/adjudicaciones.json";
  const staleMinutes = positiveNumber(
    process.env.RUN_STALE_MINUTES || process.env.STALE_MINUTES,
    30
  );
  const dataMaxAgeMinutes = positiveNumber(process.env.DATA_MAX_AGE_MINUTES, 240);
  const failureThreshold = positiveNumber(process.env.FAILURE_THRESHOLD, 1);
  const recoveryWaitMinutes = positiveNumber(process.env.RECOVERY_WAIT_MINUTES, 8);
  const dryRun = envBoolean(process.env.DRY_RUN);
  const testAlert = envBoolean(process.env.TEST_ALERT);

  if (testAlert) {
    const issueUrl = await sendTestAlert(github, owner, repo);
    core.notice(`Prueba de correo generada: ${issueUrl}`);
    core.setOutput("alert_sent", "true");
    core.setOutput("alert_url", issueUrl);
    return { action: "test_alert", issueUrl };
  }

  const monitorActive = shouldMonitor(now, context.eventName);
  core.setOutput("monitor_active", String(monitorActive));
  if (!monitorActive) {
    core.notice("Fuera del calendario o del turno de vigilancia. No se realiza ninguna accion.");
    return { action: "outside_calendar" };
  }

  let metadataBefore = { generatedAt: null, schemaVersion: null, schoolYear: null };
  let metadataError = "";
  try {
    metadataBefore = await readJsonMetadata(github, owner, repo, dataPath);
  } catch (error) {
    metadataError = error.message;
    core.warning(`No se ha podido leer generated_at: ${metadataError}`);
  }
  const generatedBefore = generatedAtHealth(metadataBefore.generatedAt, now, dataMaxAgeMinutes);

  const runs = await listPrimaryRuns(github, owner, repo, workflowId);
  const activeRuns = sortNewest(runs.filter(run => ACTIVE_STATUSES.has(run.status)));
  const staleRuns = activeRuns.filter(run => staleRunReason(run, now, staleMinutes));
  const healthyRuns = activeRuns.filter(run => !staleRunReason(run, now, staleMinutes));
  const failedRuns = consecutiveFailureRuns(runs);
  const repeatedFailures = failedRuns.length >= failureThreshold;

  core.info(`generated_at: ${metadataBefore.generatedAt || "no disponible"}`);
  core.info(`Ejecuciones activas: ${activeRuns.length}; bloqueadas: ${staleRuns.length}`);
  core.info(`Fallos consecutivos: ${failedRuns.length}; umbral: ${failureThreshold}`);
  core.info(`Limites: ejecucion ${staleMinutes} min; JSON ${dataMaxAgeMinutes} min`);

  const needsRecovery = staleRuns.length > 0 || repeatedFailures || Boolean(metadataError);
  if (!needsRecovery) {
    if (!dryRun) {
      const resolvedUrl = await resolveRecoveredIncident(
        github,
        owner,
        repo,
        metadataBefore.generatedAt,
        now
      );
      if (resolvedUrl) {
        core.notice(`Recuperacion posterior confirmada. Alerta actualizada: ${resolvedUrl}`);
        core.setOutput("alert_sent", "true");
        core.setOutput("alert_url", resolvedUrl);
        core.setOutput("recovery_succeeded", "true");
        return { action: "recovered_after_alert", issueUrl: resolvedUrl };
      }
    }
    core.notice("El workflow esta operativo. No es necesaria ninguna intervencion.");
    return { action: "healthy" };
  }

  if (dryRun) {
    core.warning("Modo de prueba: se ha detectado una posible incidencia, pero no se cancela ni relanza nada.");
    return {
      action: "dry_run",
      staleRuns: staleRuns.length,
      generatedAtStale: generatedBefore.stale,
      consecutiveFailures: failedRuns.length,
    };
  }

  if (!staleRuns.length && healthyRuns.length) {
    core.notice("Ya hay una ejecucion reciente en marcha. Se esperara a la siguiente vigilancia.");
    return { action: "healthy_run_in_progress" };
  }

  const existingIncident = await findOpenFailureIssue(github, owner, repo);
  if (existingIncident) {
    const cancelled = [];
    for (const run of staleRuns) {
      try {
        await github.rest.actions.cancelWorkflowRun({ owner, repo, run_id: run.id });
        cancelled.push(`#${run.run_number || run.id}`);
      } catch (error) {
        core.warning(`No se pudo cancelar #${run.run_number || run.id}: ${error.message}`);
      }
    }
    if (cancelled.length) {
      await github.rest.issues.createComment({
        owner,
        repo,
        issue_number: existingIncident.number,
        body: `Se cancelaron ejecuciones nuevamente bloqueadas (${cancelled.join(", ")}). No se lanza otro reintento mientras esta incidencia siga abierta.`,
      });
    }
    core.warning(`La incidencia ${existingIncident.html_url} sigue abierta; se evita encadenar nuevos reintentos.`);
    core.setOutput("alert_sent", "true");
    core.setOutput("alert_url", existingIncident.html_url);
    return { action: "incident_already_open", issueUrl: existingIncident.html_url };
  }

  const cancellationResults = [];
  for (const run of staleRuns) {
    try {
      await github.rest.actions.cancelWorkflowRun({ owner, repo, run_id: run.id });
      cancellationResults.push({ run, cancelled: true, error: "" });
    } catch (error) {
      cancellationResults.push({ run, cancelled: false, error: error.message });
    }
  }

  if (staleRuns.length) await sleepFn(15000);

  const afterCancellation = await listPrimaryRuns(github, owner, repo, workflowId);
  let recoveryRun = sortNewest(afterCancellation.filter(run =>
    ACTIVE_STATUSES.has(run.status) && !staleRunReason(run, new Date(), staleMinutes)
  ))[0] || null;
  let recoveryStarted = Boolean(recoveryRun);

  if (!recoveryRun) {
    const dispatchedAt = new Date();
    const modes = calendarModes(now).join(",");
    await github.rest.actions.createWorkflowDispatch({
      owner,
      repo,
      workflow_id: workflowId,
      ref: context.payload.repository && context.payload.repository.default_branch
        ? context.payload.repository.default_branch
        : "main",
      inputs: { force: "auto", school_year: "", recovery_modes: modes },
    });
    recoveryRun = await findNewDispatch(github, owner, repo, workflowId, dispatchedAt);
    recoveryStarted = Boolean(recoveryRun);
  }

  let finalRun = recoveryRun;
  if (recoveryRun) {
    finalRun = await waitUntilCompleted(github, owner, repo, recoveryRun.id, recoveryWaitMinutes);
  }

  let metadataAfter = { generatedAt: null, schemaVersion: null, schoolYear: null };
  let metadataAfterError = "";
  try {
    metadataAfter = await readJsonMetadata(github, owner, repo, dataPath);
  } catch (error) {
    metadataAfterError = error.message;
  }
  const generatedAfter = generatedAtHealth(
    metadataAfter.generatedAt,
    new Date(),
    dataMaxAgeMinutes
  );

  const runSucceeded = Boolean(finalRun && finalRun.status === "completed" && finalRun.conclusion === "success");
  const recoverySucceeded = runSucceeded && !metadataAfterError;
  const recoveryMessage = recoverySucceeded
    ? "La nueva comprobacion termino correctamente; si no habia documentos nuevos, generated_at puede permanecer sin cambios."
    : [
        finalRun
          ? `La ejecucion termino con estado ${finalRun.status} y resultado ${finalRun.conclusion || "sin resultado"}.`
          : "GitHub no mostro una nueva ejecucion dentro del tiempo de espera.",
        metadataAfterError
          ? `No se pudo comprobar el JSON: ${metadataAfterError}.`
          : `generated_at ${generatedAfter.stale ? "permanece antiguo" : "esta actualizado"}.`,
      ].join(" ");

  const report = buildIncidentReport({
    now,
    staleRuns,
    cancellationResults,
    generatedBefore,
    generatedAfter,
    failedRuns,
    recoveryRun: finalRun || recoveryRun,
    recoveryStarted,
    recoverySucceeded,
    recoveryMessage,
  });

  const issueUrl = await notifyIncident(github, owner, repo, recoverySucceeded, report);
  core.setOutput("alert_sent", "true");
  core.setOutput("alert_url", issueUrl);
  core.setOutput("recovery_succeeded", String(recoverySucceeded));

  if (recoverySucceeded) {
    core.notice(`Recuperacion correcta. Alerta enviada: ${issueUrl}`);
  } else {
    core.warning(`La recuperacion fallo. Alerta enviada: ${issueUrl}`);
  }
  return { action: "recovery", recoverySucceeded, issueUrl };
}

module.exports = runWatchdog;
module.exports._test = {
  ageMinutes,
  buildIncidentReport,
  calendarModes,
  consecutiveFailureRuns,
  envBoolean,
  generatedAtHealth,
  madridCalendar,
  positiveNumber,
  runAgeMinutes,
  shouldMonitor,
  staleRunReason,
};
