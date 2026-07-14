"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const runWatchdog = require("./watchdog-adjudicaciones.js");
const {
  buildIncidentReport,
  generatedAtHealth,
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
  process.env.STALE_MINUTES = "30";
  process.env.RECOVERY_WAIT_MINUTES = "8";
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

test("vigila todos los dias de julio y agosto", () => {
  assert.equal(shouldMonitor(new Date("2026-07-15T12:00:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-08-16T12:00:00Z"), "schedule"), true);
});

test("de septiembre a junio solo vigila martes y jueves", () => {
  assert.equal(shouldMonitor(new Date("2026-09-01T12:00:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-09-03T12:00:00Z"), "schedule"), true);
  assert.equal(shouldMonitor(new Date("2026-09-02T12:00:00Z"), "schedule"), false);
});

test("las comprobaciones manuales siempre estan permitidas", () => {
  assert.equal(shouldMonitor(new Date("2026-09-02T12:00:00Z"), "workflow_dispatch"), true);
});

test("el respaldo workflow_run comprueba una de cada dos finalizaciones", () => {
  const july = new Date("2026-07-14T12:00:00Z");
  assert.equal(shouldMonitor(july, "workflow_run", 772), true);
  assert.equal(shouldMonitor(july, "workflow_run", 773), false);
  assert.equal(shouldMonitor(new Date("2026-09-02T12:00:00Z"), "workflow_run", 774), false);
});

test("solo considera bloqueada una cola de mas de treinta minutos", () => {
  const now = new Date("2026-07-14T12:00:00Z");
  assert.match(staleRunReason({ status: "queued", created_at: isoMinutesBefore(now, 31) }, now, 30), /31 minutos/);
  assert.equal(staleRunReason({ status: "queued", created_at: isoMinutesBefore(now, 29) }, now, 30), "");
  assert.match(staleRunReason({ status: "in_progress", run_started_at: isoMinutesBefore(now, 31) }, now, 30), /ejecucion/);
});

test("detecta generated_at retrasado o no valido", () => {
  const now = new Date("2026-07-14T12:00:00Z");
  assert.equal(generatedAtHealth(isoMinutesBefore(now, 31), now, 30).stale, true);
  assert.equal(generatedAtHealth(isoMinutesBefore(now, 5), now, 30).stale, false);
  assert.equal(generatedAtHealth("fecha-invalida", now, 30).stale, true);
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
    recoveryRun: { ...run, id: 900, run_number: 900, status: "completed", conclusion: "success" },
    recoveryStarted: true,
    recoverySucceeded: true,
    recoveryMessage: "Correcto.",
  });
  assert.match(report, /Ejecucion bloqueada/);
  assert.match(report, /cancelada automaticamente/);
  assert.match(report, /Nueva ejecucion/);
  assert.match(report, /RECUPERACION CORRECTA/);
});

test("simula cancelacion, relanzamiento y recuperacion correcta", async () => {
  setWatchdogEnv();
  const now = new Date();
  const { github, calls } = recoveryGithub(now, "success");
  const core = fakeCore();
  const result = await runWatchdog({ github, context: context(), core, now, sleepFn: async () => {} });

  assert.equal(result.action, "recovery");
  assert.equal(result.recoverySucceeded, true);
  assert.equal(calls.cancel.length, 1);
  assert.equal(calls.cancel[0].run_id, 751);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(calls.dispatch[0].workflow_id, "update-adjudicaciones.yml");
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
  const result = await runWatchdog({ github, context: context(), core, now, sleepFn: async () => {} });

  assert.equal(result.recoverySucceeded, false);
  assert.equal(calls.cancel.length, 1);
  assert.equal(calls.dispatch.length, 1);
  assert.equal(calls.issues[0].title, "[AdjudicApp] Recuperacion automatica fallida");
  assert.equal(calls.issueUpdates.length, 0);
  assert.equal(core.records.outputs.recovery_succeeded, "false");
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
  const result = await runWatchdog({ github, context: context(), core, now, sleepFn: async () => {} });

  assert.equal(result.action, "recovered_after_alert");
  assert.equal(calls.comments.length, 1);
  assert.match(calls.comments[0].body, /RECUPERACION CONFIRMADA/);
  assert.equal(calls.issueUpdates.length, 1);
  assert.equal(calls.issueUpdates[0].state, "closed");
  assert.equal(core.records.outputs.recovery_succeeded, "true");
});
