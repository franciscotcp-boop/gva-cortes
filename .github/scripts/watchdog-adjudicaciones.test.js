"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const runWatchdog = require("./watchdog-adjudicaciones.js");
const {
  buildIncidentReport,
  calendarModes,
  dueScheduledChecks,
  consecutiveFailureRuns,
  generatedAtHealth,
  missedScheduledChecks,
  readRunReceipt,
  receiptSuccessfulModes,
  validateRunReceipt,
  recoveryModesForRun,
  recoveryIncidentAge,
  shouldMonitor,
  staleRunReason,
} = runWatchdog._test;

function isoMinutesBefore(now, minutes) {
  return new Date(now.getTime() - minutes * 60000).toISOString();
}

function encodedJson(generatedAt) {
  return Buffer.from(JSON.stringify({
    generated_at: generatedAt,
    schema_version: 3,
    cuts: { inicio: { school_year: "2025-2026" } },
  })).toString("base64");
}

function fakeCore() {
  const records = { info: [], notices: [], warnings: [], outputs: {} };
  return {
    records,
    info: value => records.info.push(value),
    notice: value => records.notices.push(value),
    warning: value => records.warnings.push(value),
    setOutput: (name, value) => { records.outputs[name] = value; },
  };
}

function context() {
  return {
    eventName: "schedule",
    repo: { owner: "franciscotcp-boop", repo: "gva-cortes" },
    payload: { repository: { default_branch: "main" } },
  };
}

function setWatchdogEnv() {
  process.env.PRIMARY_WORKFLOW = "update-adjudicaciones.yml";
  process.env.DATA_PATH = "data/adjudicaciones.json";
  process.env.RUN_STALE_MINUTES = "30";
  process.env.DATA_MAX_AGE_MINUTES = "240";
  process.env.FAILURE_THRESHOLD = "1";
  process.env.RECOVERY_WAIT_MINUTES = "15";
  process.env.DRY_RUN = "false";
  process.env.TEST_ALERT = "false";
}

function recoveryGithub(now, conclusion = "success") {
  const calls = {
    cancel: [],
    dispatch: [],
    issues: [],
    issueUpdates: [],
  };
  let contentRead = 0;
  let runsRead = 0;
  const staleRun = {
    id: 751,
    run_number: 751,
    status: "queued",
    conclusion: null,
    created_at: isoMinutesBefore(now, 35),
    html_url: "https://github.com/example/actions/runs/751",
    event: "schedule",
    display_title: "Actualizar adjudicaciones (schedule)",
  };
  const replacementRun = {
    id: 900,
    run_number: 900,
    status: "queued",
    conclusion: null,
    created_at: new Date().toISOString(),
    html_url: "https://github.com/example/actions/runs/900",
    event: "workflow_dispatch",
    display_title: "Actualizar adjudicaciones (automatico)",
  };

  const github = {
    rest: {
      repos: {
        getContent: async () => {
          contentRead += 1;
          const generatedAt = contentRead === 1 || conclusion !== "success"
            ? isoMinutesBefore(now, 40)
            : new Date().toISOString();
          return { data: { content: encodedJson(generatedAt), sha: "blob-sha" } };
        },
      },
      git: {
        getBlob: async () => { throw new Error("No deberia usarse getBlob en esta prueba"); },
      },
      actions: {
        listJobsForWorkflowRun: async () => ({ data: { jobs: [{ steps: [
          { name: "Actualizar puestos ofertados", conclusion: "success" },
        ] }] } }),
        listWorkflowRuns: async () => {
          runsRead += 1;
          if (runsRead === 1) return { data: { workflow_runs: [staleRun] } };
          if (runsRead === 2) return { data: { workflow_runs: [] } };
          return { data: { workflow_runs: [replacementRun] } };
        },
        cancelWorkflowRun: async args => { calls.cancel.push(args); return { status: 202 }; },
        createWorkflowDispatch: async args => { calls.dispatch.push(args); return { status: 204 }; },
        getWorkflowRun: async () => ({
          data: {
            ...replacementRun,
            status: "completed",
            conclusion,
          },
        }),
      },
      issues: {
        listForRepo: async () => ({ data: [] }),
        create: async args => {
          calls.issues.push(args);
          return { data: { number: 12, html_url: "https://github.com/example/issues/12" } };
        },
        createComment: async () => { throw new Error("No deberia reutilizar una incidencia"); },
        update: async args => { calls.issueUpdates.push(args); return { data: {} }; },
      },
    },
  };
  return { github, calls };
}

test("vigila julio a diario por posiciones y agosto salvo domingos", () => {
  assert.equal(shouldMonitor(new Date("2026-07-15T07:30:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-08-15T07:30:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-08-16T07:30:00Z"), "schedule"), false);
});

test("calcula las fuentes activas de cada fecha", () => {
  assert.deepEqual(
    calendarModes(new Date("2026-07-17T10:00:00Z")),
    ["inicio", "acreditaciones"]
  );
  assert.deepEqual(calendarModes(new Date("2026-09-04T12:00:00Z")), ["acreditaciones", "dificil"]);
});

test("de septiembre a junio vigila adjudicaciones y puestos ofertados", () => {
  assert.equal(shouldMonitor(new Date("2026-09-01T10:30:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-09-03T10:30:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-09-02T09:30:00Z"), "schedule"), true);
  assert.deepEqual(calendarModes(new Date("2026-09-02T09:30:00Z")), ["puestos"]);
  assert.deepEqual(calendarModes(new Date("2026-09-02T18:00:00Z")), ["puestos"]);
});

test("los puestos ofertados terminan el uno de julio", () => {
  assert.deepEqual(
    calendarModes(new Date("2026-07-01T07:00:00Z")),
    ["inicio", "posiciones", "puestos"]
  );
  assert.deepEqual(
    calendarModes(new Date("2026-07-08T07:00:00Z")),
    ["inicio", "posiciones"]
  );
});

test("vigila dificil cobertura hasta las 23 y la retira al cambiar de dia", () => {
  assert.deepEqual(
    calendarModes(new Date("2026-09-04T21:30:00Z")),
    ["dificil"]
  );
  assert.deepEqual(
    calendarModes(new Date("2026-09-04T22:30:00Z")),
    ["limpieza_puestos"]
  );
});

test("las comprobaciones manuales siempre estan permitidas", () => {
  assert.equal(shouldMonitor(new Date("2026-09-02T12:00:00Z"), "workflow_dispatch"), true);
});

test("solo considera bloqueada una cola de mas de treinta minutos", () => {
  const now = new Date("2026-07-14T12:00:00Z");
  assert.match(staleRunReason({ status: "queued", created_at: isoMinutesBefore(now, 31) }, now, 30), /31 minutos/);
  assert.equal(staleRunReason({ status: "queued", created_at: isoMinutesBefore(now, 29) }, now, 30), "");
  assert.match(staleRunReason({ status: "in_progress", run_started_at: isoMinutesBefore(now, 31) }, now, 30), /ejecucion/);
});

test("detecta generated_at retrasado o no valido", () => {
  const now = new Date("2026-07-14T12:00:00Z");
  assert.equal(generatedAtHealth(isoMinutesBefore(now, 241), now, 240).stale, true);
  assert.equal(generatedAtHealth(isoMinutesBefore(now, 239), now, 240).stale, false);
  assert.equal(generatedAtHealth("fecha-invalida", now, 240).stale, true);
});

test("detecta fallos consecutivos aunque haya ejecuciones activas o canceladas", () => {
  const now = new Date("2026-07-15T12:00:00Z");
  const runs = [
    { id: 8, status: "in_progress", conclusion: null, created_at: isoMinutesBefore(now, 1) },
    { id: 7, status: "completed", conclusion: "failure", created_at: isoMinutesBefore(now, 5) },
    { id: 6, status: "completed", conclusion: "cancelled", created_at: isoMinutesBefore(now, 6) },
    { id: 5, status: "completed", conclusion: "timed_out", created_at: isoMinutesBefore(now, 10) },
    { id: 4, status: "completed", conclusion: "failure", created_at: isoMinutesBefore(now, 15) },
    { id: 3, status: "completed", conclusion: "success", created_at: isoMinutesBefore(now, 20) },
    { id: 2, status: "completed", conclusion: "failure", created_at: isoMinutesBefore(now, 25) },
  ];

  assert.deepEqual(consecutiveFailureRuns(runs).map(run => run.id), [7, 5, 4]);
});

test("el informe contiene bloqueo, cancelacion, relanzamiento y resultado", () => {
  const now = new Date("2026-07-14T12:00:00Z");
  const run = { id: 751, run_number: 751, status: "queued", created_at: isoMinutesBefore(now, 35) };
  const report = buildIncidentReport({
    now,
    staleRuns: [run],
    cancellationResults: [{ run, cancelled: true, error: "" }],
    generatedBefore: generatedAtHealth(isoMinutesBefore(now, 40), now, 30),
    generatedAfter: generatedAtHealth(now.toISOString(), now, 30),
    failedRuns: [{ ...run, status: "completed", conclusion: "failure" }],
    recoveryRun: { ...run, id: 900, run_number: 900, status: "completed", conclusion: "success" },
    recoveryStarted: true,
    recoverySucceeded: true,
    recoveryMessage: "Correcto.",
  });
  assert.match(report, /Ejecucion bloqueada/);
  assert.match(report, /cancelada automaticamente/);
  assert.match(report, /Fallos consecutivos/);
  assert.match(report, /Nueva ejecucion/);
  assert.match(report, /RECUPERACION CORRECTA/);
});

test("simula cancelacion, relanzamiento y recuperacion correcta", async () => {
  setWatchdogEnv();
  const now = new Date();
  const { github, calls } = recoveryGithub(now, "success");
  const core = fakeCore();
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const result = await runWatchdog({ github, context: manualContext, core, now, sleepFn: async () => {}, auditSchedule: false });

  assert.equal(result.action, "recovery");
  assert.equal(result.recoverySucceeded, true);
  assert.equal(calls.cancel.length, 1);
  assert.equal(calls.cancel[0].run_id, 751);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(calls.dispatch[0].workflow_id, "update-adjudicaciones.yml");
  assert.deepEqual(calls.dispatch[0].inputs, {
    force: "auto",
    school_year: "",
    recovery_modes: "puestos",
  });
  assert.equal(calls.issues.length, 1);
  assert.equal(calls.issues[0].assignees[0], "franciscotcp-boop");
  assert.equal(calls.issueUpdates.length, 1);
  assert.equal(core.records.outputs.recovery_succeeded, "true");
});

test("simula una recuperacion fallida y deja una alerta abierta", async () => {
  setWatchdogEnv();
  const now = new Date();
  const { github, calls } = recoveryGithub(now, "failure");
  const core = fakeCore();
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const result = await runWatchdog({ github, context: manualContext, core, now, sleepFn: async () => {}, auditSchedule: false });

  assert.equal(result.recoverySucceeded, false);
  assert.equal(calls.cancel.length, 1);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(calls.issues[0].title, "[AdjudicApp] Recuperacion automatica fallida");
  assert.equal(calls.issueUpdates.length, 0);
  assert.equal(core.records.outputs.recovery_succeeded, "false");
});

test("recupera la fuente original aunque el fallo termine fuera del turno", async () => {
  const now = new Date("2026-09-07T14:10:00Z");
  assert.deepEqual(calendarModes(now), []);
  const github = { rest: { actions: {
    listJobsForWorkflowRun: async () => ({ data: { jobs: [{ steps: [
      { name: "Actualizar puestos ofertados", conclusion: "success" },
      { name: "Actualizar cortes de adjudicaciones", conclusion: "skipped" },
      { name: "Comunicar fallos de las fuentes al vigilante", conclusion: "failure" },
    ] }] } }),
  } } };
  assert.deepEqual(await recoveryModesForRun(github, "owner", "repo", {
    id: 1631, created_at: "2026-09-07T13:27:34Z", event: "schedule",
  }, now), ["puestos"]);
});

test("el evento de finalizacion activa la recuperacion fuera del calendario", async () => {
  setWatchdogEnv();
  const now = new Date("2026-09-07T14:10:00Z");
  const { github, calls } = recoveryGithub(now);
  const eventContext = context();
  eventContext.eventName = "workflow_run";
  const result = await runWatchdog({
    github, context: eventContext, core: fakeCore(), now, sleepFn: async () => {}, auditSchedule: false,
  });
  assert.equal(result.recoverySucceeded, true);
  assert.equal(calls.dispatch[0].inputs.recovery_modes, "puestos");
});

test("espera si tras un fallo ya hay una ejecucion reciente en marcha", async () => {
  setWatchdogEnv();
  const now = new Date();
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const calls = { cancel: [], dispatch: [], issues: [] };
  const activeRun = {
    id: 950,
    run_number: 950,
    status: "in_progress",
    conclusion: null,
    created_at: isoMinutesBefore(now, 2),
    run_started_at: isoMinutesBefore(now, 2),
    html_url: "https://github.com/example/actions/runs/950",
    event: "workflow_dispatch",
    display_title: "Actualizar adjudicaciones (automatico)",
  };
  const failures = [1, 2, 3].map((value, index) => ({
    id: 949 - index,
    run_number: 949 - index,
    status: "completed",
    conclusion: "failure",
    created_at: isoMinutesBefore(now, 7 + index * 5),
    html_url: `https://github.com/example/actions/runs/${949 - index}`,
  }));
  const previousSuccess = {
    id: 940,
    status: "completed",
    conclusion: "success",
    created_at: isoMinutesBefore(now, 35),
  };
  const github = {
    rest: {
      repos: {
        getContent: async () => ({
          data: { content: encodedJson(isoMinutesBefore(now, 250)), sha: "blob-sha" },
        }),
      },
      git: {
        getBlob: async () => { throw new Error("No deberia usarse getBlob en esta prueba"); },
      },
      actions: {
        listWorkflowRuns: async () => ({
          data: { workflow_runs: [activeRun, ...failures, previousSuccess] },
        }),
        cancelWorkflowRun: async args => { calls.cancel.push(args); },
        createWorkflowDispatch: async args => { calls.dispatch.push(args); },
        getWorkflowRun: async () => ({
          data: { ...activeRun, status: "completed", conclusion: "failure" },
        }),
      },
      issues: {
        listForRepo: async () => ({ data: [] }),
        create: async args => {
          calls.issues.push(args);
          return { data: { number: 22, html_url: "https://github.com/example/issues/22" } };
        },
        createComment: async () => { throw new Error("No deberia reutilizar una incidencia"); },
        update: async () => { throw new Error("No debe cerrar una recuperacion fallida"); },
      },
    },
  };
  const core = fakeCore();
  const result = await runWatchdog({ github, context: manualContext, core, now, sleepFn: async () => {}, auditSchedule: false });

  assert.equal(result.action, "healthy_run_in_progress");
  assert.equal(calls.cancel.length, 0);
  assert.equal(calls.dispatch.length, 0);
  assert.equal(calls.issues.length, 0);
  assert.match(core.records.notices.join("\n"), /ejecucion reciente en marcha/);
});

test("confirma por correo una recuperacion que termino despues del primer aviso", async () => {
  setWatchdogEnv();
  const now = new Date();
  const calls = { comments: [], issueUpdates: [] };
  const github = {
    rest: {
      repos: {
        getContent: async () => ({
          data: { content: encodedJson(now.toISOString()), sha: "blob-sha" },
        }),
      },
      git: {
        getBlob: async () => { throw new Error("No deberia usarse getBlob en esta prueba"); },
      },
      actions: {
        listWorkflowRuns: async () => ({ data: { workflow_runs: [] } }),
      },
      issues: {
        listForRepo: async () => ({
          data: [{
            number: 18,
            title: "[AdjudicApp] Recuperacion automatica fallida",
            html_url: "https://github.com/example/issues/18",
          }],
        }),
        createComment: async args => { calls.comments.push(args); return { data: {} }; },
        update: async args => { calls.issueUpdates.push(args); return { data: {} }; },
      },
    },
  };
  const core = fakeCore();
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const result = await runWatchdog({ github, context: manualContext, core, now, sleepFn: async () => {}, auditSchedule: false });

  assert.equal(result.action, "recovered_after_alert");
  assert.equal(calls.comments.length, 1);
  assert.match(calls.comments[0].body, /RECUPERACION CONFIRMADA/);
  assert.equal(calls.issueUpdates.length, 1);
  assert.equal(calls.issueUpdates[0].state, "closed");
  assert.equal(core.records.outputs.recovery_succeeded, "true");
});

test("detecta el turno omitido aunque el vigilante llegue fuera de su hora", () => {
  const now = new Date("2026-09-30T14:10:00Z");
  assert.deepEqual(calendarModes(now), []);
  assert.equal(shouldMonitor(now), true);
  assert.deepEqual(dueScheduledChecks(now), [{ mode: "puestos", scheduledAt: "2026-09-30T13:37:00.000Z" }]);
  assert.deepEqual(dueScheduledChecks(new Date("2026-09-30T07:30:00Z")), []);
  assert.deepEqual(dueScheduledChecks(new Date("2026-09-30T07:37:00Z")), [{ mode: "puestos", scheduledAt: "2026-09-30T07:07:00.000Z" }]);
});

test("los turnos pendientes respetan Madrid en invierno y no arrastran dificil cobertura al sabado", () => {
  assert.deepEqual(dueScheduledChecks(new Date("2026-10-28T09:10:00Z")), [{ mode: "puestos", scheduledAt: "2026-10-28T08:07:00.000Z" }]);
  assert.deepEqual(dueScheduledChecks(new Date("2026-09-26T22:30:00Z")), []);
  assert.deepEqual(dueScheduledChecks(new Date("2026-09-25T23:00:00Z")), [{ mode: "limpieza_puestos", scheduledAt: "2026-09-25T22:20:00.000Z" }]);
});

test("recupera el ultimo turno del dia tras mas de tres horas sin eventos", () => {
  const delayedMidday = new Date("2026-10-01T16:18:00Z");
  const morning = [{ mode: "curso", scheduledAt: "2026-10-01T13:17:00.000Z" }];
  assert.deepEqual(dueScheduledChecks(delayedMidday), morning);
  assert.deepEqual(dueScheduledChecks(delayedMidday, 30, 180), []);
  const now = new Date("2026-10-01T21:50:00Z");
  const expected = [{ mode: "curso", scheduledAt: "2026-10-01T19:17:00.000Z" }];
  assert.deepEqual(dueScheduledChecks(now), expected);
  const delayed = new Date("2026-10-01T21:59:00Z");
  assert.deepEqual(calendarModes(delayed), []);
  assert.equal(shouldMonitor(delayed), true);
  const gap = new Date("2026-10-01T15:58:00Z");
  assert.deepEqual(dueScheduledChecks(gap, 30, 30), []);
  assert.equal(shouldMonitor(gap, "schedule", 30, 30), false);
  assert.equal(shouldMonitor(gap, "schedule", 30, 1440), true);
  assert.deepEqual(dueScheduledChecks(new Date("2026-10-01T22:10:00Z")), []);
});

test("un JSON reciente o una ejecucion de otra fuente no ocultan puestos sin revisar", async () => {
  const now = new Date("2026-09-30T14:10:00Z");
  const checks = dueScheduledChecks(now);
  const run = { id: 1, status: "completed", conclusion: "success", created_at: "2026-09-30T13:50:00Z" };
  let steps = [{ name: "Actualizar cortes de adjudicaciones", conclusion: "success", started_at: "2026-09-30T13:51:00Z" }];
  const github = { rest: { actions: { listJobsForWorkflowRun: async () => ({ data: { jobs: [{ conclusion: "success", steps }] } }) } } };
  assert.deepEqual(await missedScheduledChecks(github, "owner", "repo", [run], checks, now), checks);
  steps = [{ name: "Actualizar puestos ofertados", conclusion: "skipped", started_at: "2026-09-30T13:51:00Z" }];
  assert.deepEqual(await missedScheduledChecks(github, "owner", "repo", [run], checks, now), checks);
  steps[0].conclusion = "success";
  assert.deepEqual(await missedScheduledChecks(github, "owner", "repo", [run], checks, now), []);
  assert.deepEqual(await missedScheduledChecks(github, "owner", "repo", [{ ...run, conclusion: "failure" }], checks, now), checks);
  steps[0].started_at = "2026-09-30T10:00:00Z";
  assert.deepEqual(await missedScheduledChecks(github, "owner", "repo", [run], checks, now), checks);
});

test("recupera una fuente omitida sin cancelar ni repetir otras fuentes", async () => {
  setWatchdogEnv();
  const now = new Date("2026-09-30T12:10:00Z");
  const { github, calls } = recoveryGithub(now);
  const replacement = { id: 900, created_at: new Date().toISOString(), event: "workflow_dispatch", status: "queued" };
  let scans = 0;
  github.rest.actions.listWorkflowRuns = async () => ({ data: { workflow_runs: ++scans < 3 ? [] : [replacement] } });
  const result = await runWatchdog({ github, context: context(), core: fakeCore(), now });
  assert.equal(result.recoverySucceeded, true);
  assert.equal(calls.cancel.length, 0);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(calls.dispatch[0].inputs.recovery_modes, "puestos");
  assert.match(calls.issues[0].body, /Turnos sin comprobacion confirmada/);
});

test("no confirma una recuperacion verde que omitio la fuente pendiente", async () => {
  setWatchdogEnv();
  const now = new Date("2026-09-30T12:10:00Z");
  const { github, calls } = recoveryGithub(now);
  const replacement = { id: 900, created_at: new Date().toISOString(), event: "workflow_dispatch", status: "queued" };
  let scans = 0;
  github.rest.actions.listWorkflowRuns = async () => ({ data: { workflow_runs: ++scans < 3 ? [] : [replacement] } });
  github.rest.actions.listJobsForWorkflowRun = async () => ({ data: { jobs: [{ steps: [{ name: "Actualizar puestos ofertados", conclusion: "skipped" }] }] } });
  const result = await runWatchdog({ github, context: context(), core: fakeCore(), now });
  assert.equal(result.recoverySucceeded, false);
  assert.match(calls.issues[0].body, /No se han comprobado correctamente todas las fuentes pendientes/);
});

test("el comprobante debe pertenecer a la ejecucion, intento y codigo exactos", () => {
  const run = { id: 17, run_attempt: 2, head_sha: "abc" };
  const receipt = { schema_version: 1, run_id: 17, run_attempt: 2, head_sha: "abc",
    checked_at: "2026-09-30T12:10:00Z", modes: ["puestos"], source_outcomes: { puestos: "success" },
    validation_outcome: "success", publication_outcome: "success" };
  assert.equal(validateRunReceipt(receipt, run), true);
  assert.equal(validateRunReceipt({ ...receipt, run_attempt: 1 }, run), false);
  assert.equal(validateRunReceipt({ ...receipt, head_sha: "other" }, run), false);
  assert.equal(validateRunReceipt({ ...receipt, modes: ["unknown"] }, run), false);
  assert.deepEqual(receiptSuccessfulModes(receipt), ["puestos"]);
  assert.deepEqual(receiptSuccessfulModes({ ...receipt, publication_outcome: "failure" }), []);
  assert.deepEqual(receiptSuccessfulModes({ ...receipt, source_outcomes: { puestos: "skipped" } }), []);
});

test("lee el comprobante propio cuando GitHub omite los pasos de los jobs", async () => {
  const run = { id: 17, run_attempt: 2, head_sha: "abc" };
  const receipt = { schema_version: 1, run_id: 17, run_attempt: 2, head_sha: "abc",
    checked_at: "2026-09-30T12:10:00Z", modes: ["puestos"], source_outcomes: { puestos: "success" } };
  const github = { rest: { actions: {
    listWorkflowRunArtifacts: async () => ({ data: { artifacts: [
      { id: 1, name: "automation-check-17-1" },
      { id: 2, name: "automation-check-17-2", expired: false },
    ] } }),
    downloadArtifact: async args => { assert.equal(args.artifact_id, 2); return { data: Buffer.from("archive") }; },
  } } };
  assert.deepEqual(await readRunReceipt(github, "owner", "repo", run, () => receipt), receipt);
  await assert.rejects(readRunReceipt(github, "owner", "repo", run, () => ({ ...receipt, run_id: 16 })), /Comprobante no valido/);
});

test("recupera cada turno de media hora en los picos de publicacion", () => {
  const cases = [
    ["2026-10-05", "puestos", [13, 14, 15], [7, 37]],
    ["2026-10-07", "puestos", [13, 14, 15], [7, 37]],
    ["2026-10-06", "curso", [9, 10, 11, 12, 13, 14], [17, 47]],
    ["2026-10-08", "curso", [9, 10, 11, 12, 13, 14], [17, 47]],
    ["2026-10-02", "dificil", [13, 14, 15], [20, 50]],
  ];
  for (const [day, mode, hours, minutes] of cases) {
    for (const hour of hours) for (const minute of minutes) {
      const local = new Date(`${day}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+02:00`);
      const checks = dueScheduledChecks(new Date(local.getTime() + 15 * 60000), 15);
      assert.deepEqual(checks.find(check => check.mode === mode), { mode, scheduledAt: local.toISOString() });
    }
  }
  assert.deepEqual(dueScheduledChecks(new Date("2026-12-02T13:52:00Z"), 15), [
    { mode: "puestos", scheduledAt: "2026-12-02T13:37:00.000Z" },
  ]);
});

test("una incidencia reciente espera la pausa sin despachar otra ejecucion", async () => {
  setWatchdogEnv();
  const now = new Date();
  const { github, calls } = recoveryGithub(now);
  const failure = { id: 1, status: "completed", conclusion: "failure", created_at: isoMinutesBefore(now, 20) };
  github.rest.actions.listWorkflowRuns = async () => ({ data: { workflow_runs: [failure] } });
  github.rest.issues.listForRepo = async () => ({ data: [{ number: 12, title: "[AdjudicApp] Recuperacion automatica fallida",
    updated_at: isoMinutesBefore(now, 30), html_url: "https://github.com/example/issues/12" }] });
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const result = await runWatchdog({ github, context: manualContext, core: fakeCore(), now, auditSchedule: false });
  assert.equal(result.action, "incident_already_open");
  assert.equal(calls.dispatch.length, 0);
  assert.equal(calls.cancel.length, 0);
  assert.equal(calls.issues.length, 0);
});

test("una alerta abierta no bloquea indefinidamente la recuperacion", async () => {
  setWatchdogEnv();
  const now = new Date();
  const { github, calls } = recoveryGithub(now);
  const incident = { number: 12, title: "[AdjudicApp] Recuperacion automatica fallida",
    updated_at: isoMinutesBefore(now, 61), html_url: "https://github.com/example/issues/12" };
  github.rest.issues.listForRepo = async () => ({ data: [incident] });
  const comments = [];
  github.rest.issues.createComment = async args => { comments.push(args); return { data: {} }; };
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const result = await runWatchdog({ github, context: manualContext, core: fakeCore(), now, sleepFn: async () => {}, auditSchedule: false });
  assert.equal(result.recoverySucceeded, true);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(calls.issues.length, 0);
  assert.equal(comments.length, 1);
  assert.equal(calls.issueUpdates[0].state, "closed");
});

test("un reintento fallido conserva la alerta y el periodo de pausa", async () => {
  setWatchdogEnv();
  const now = new Date();
  const { github, calls } = recoveryGithub(now, "failure");
  const incident = { number: 12, title: "[AdjudicApp] Recuperacion automatica fallida",
    updated_at: isoMinutesBefore(now, 61), html_url: "https://github.com/example/issues/12" };
  github.rest.issues.listForRepo = async () => ({ data: [incident] });
  const comments = [];
  github.rest.issues.createComment = async args => { comments.push(args); return { data: {} }; };
  const manualContext = context();
  manualContext.eventName = "workflow_dispatch";
  const result = await runWatchdog({ github, context: manualContext, core: fakeCore(), now, sleepFn: async () => {}, auditSchedule: false });
  assert.equal(result.recoverySucceeded, false);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(comments.length, 1);
  assert.equal(calls.issueUpdates.length, 1);
  assert.equal(calls.issueUpdates[0].state, undefined);
  assert.match(calls.issueUpdates[0].body, /adjudicapp-recovery-at:/);
});

test("otros comentarios y cancelaciones no reinician la pausa de recuperacion", () => {
  const now = new Date("2026-10-01T12:00:00Z");
  const issue = { created_at: "2026-10-01T08:00:00Z", updated_at: "2026-10-01T11:59:00Z",
    body: "<!-- adjudicapp-recovery-at: 2026-10-01T10:00:00.000Z -->\nInforme" };
  assert.equal(recoveryIncidentAge(issue, now), 120);
  assert.equal(recoveryIncidentAge({ ...issue, body: "Informe antiguo" }, now), 240);
  assert.equal(recoveryIncidentAge({ ...issue, body: "<!-- adjudicapp-recovery-at: invalid -->" }, now), 240);
});

test("el aviso de una bolsa dudosa incluye el puesto y las opciones concretas", () => {
  const now = new Date("2026-10-01T12:00:00Z");
  const report = buildIncidentReport({
    now, staleRuns: [], cancellationResults: [],
    generatedBefore: generatedAtHealth(now.toISOString(), now),
    generatedAfter: generatedAtHealth(now.toISOString(), now),
    recoveryStarted: false, recoverySucceeded: false, recoveryMessage: "Se necesita confirmacion.",
    programReviews: [{ candidate_name: "VICEDO DURA, GUILLERMO", slot_id: "841479", center_code: "03012980",
      post_specialty_code: "297", candidate_pools: [{ specialty_code: "211", position: 7 }, { specialty_code: "256", position: 230 }] }],
  });
  assert.match(report, /Bolsas de origen pendientes de tu confirmacion/);
  assert.match(report, /VICEDO DURA, GUILLERMO; puesto 841479/);
  assert.match(report, /211 \(posicion 7\), 256 \(posicion 230\)/);
  assert.match(report, /ultimos datos validos/);
});
