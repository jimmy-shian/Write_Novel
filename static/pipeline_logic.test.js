const test = require("node:test");
const assert = require("node:assert/strict");

const { getPipelinePrompt, resolveNextStageFromDecision } = require("./pipeline_logic");

// ==========================================
// getPipelinePrompt 測試
// ==========================================

test("getPipelinePrompt: 使用者輸入優先於 state/DB", () => {
  const p = getPipelinePrompt({
    inputPrompt: "  A  ",
    statePrompt: "STATE",
    dbPrompt: "DB",
    fallbackPrompt: "FALLBACK",
  });
  assert.equal(p, "A");
});

test("getPipelinePrompt: state.pipelinePrompt 優先於 DB", () => {
  const p = getPipelinePrompt({
    inputPrompt: "   ",
    statePrompt: "STATE",
    dbPrompt: "DB",
    fallbackPrompt: "FALLBACK",
  });
  assert.equal(p, "STATE");
});

test("getPipelinePrompt: DB pipeline_prompt 優先於 fallback", () => {
  const p = getPipelinePrompt({
    inputPrompt: "",
    statePrompt: "",
    dbPrompt: "DB",
    fallbackPrompt: "FALLBACK",
  });
  assert.equal(p, "DB");
});

test("getPipelinePrompt: fallback 作為最後備援", () => {
  const p = getPipelinePrompt({
    inputPrompt: "",
    statePrompt: "",
    dbPrompt: "",
    fallbackPrompt: "DEFAULT_PROMPT",
  });
  assert.equal(p, "DEFAULT_PROMPT");
});

test("getPipelinePrompt: 全空白輸入回退到 fallback", () => {
  const p = getPipelinePrompt({
    inputPrompt: "   \n\t  ",
    statePrompt: "  \n  ",
    dbPrompt: "  ",
    fallbackPrompt: "FINAL",
  });
  assert.equal(p, "FINAL");
});

// ==========================================
// resolveNextStageFromDecision 測試
// ==========================================

// CONTINUE 動作測試
test("resolveNextStageFromDecision: CONTINUE 從 worldview → characters", () => {
  const result = resolveNextStageFromDecision({ action: 'CONTINUE' }, 'worldview');
  assert.equal(result, 'characters');
});

test("resolveNextStageFromDecision: CONTINUE 從 characters → plot", () => {
  const result = resolveNextStageFromDecision({ action: 'CONTINUE' }, 'characters');
  assert.equal(result, 'plot');
});

test("resolveNextStageFromDecision: CONTINUE 從 plot → writer", () => {
  const result = resolveNextStageFromDecision({ action: 'CONTINUE' }, 'plot');
  assert.equal(result, 'writer');
});

test("resolveNextStageFromDecision: CONTINUE 從 writer → null (完成)", () => {
  const result = resolveNextStageFromDecision({ action: 'CONTINUE' }, 'writer');
  assert.equal(result, null);
});

test("resolveNextStageFromDecision: CONTINUE 未知階段預設回 worldview", () => {
  const result = resolveNextStageFromDecision({ action: 'CONTINUE' }, 'unknown');
  assert.equal(result, 'worldview');
});

// AUTO_REGENERATE 動作測試
test("resolveNextStageFromDecision: AUTO_REGENERATE 保持當前階段", () => {
  const result = resolveNextStageFromDecision({ action: 'AUTO_REGENERATE' }, 'worldview');
  assert.equal(result, 'worldview');
});

test("resolveNextStageFromDecision: AUTO_REGENERATE 無 currentStage 預設 worldview", () => {
  const result = resolveNextStageFromDecision({ action: 'AUTO_REGENERATE' }, null);
  assert.equal(result, 'worldview');
});

// GO_BACK 動作測試
test("resolveNextStageFromDecision: GO_BACK_TO_WORLDVIEW 返回 worldview", () => {
  const result = resolveNextStageFromDecision({ action: 'GO_BACK_TO_WORLDVIEW' }, 'writer');
  assert.equal(result, 'worldview');
});

test("resolveNextStageFromDecision: GO_BACK_TO_CHARACTERS 返回 characters", () => {
  const result = resolveNextStageFromDecision({ action: 'GO_BACK_TO_CHARACTERS' }, 'writer');
  assert.equal(result, 'characters');
});

test("resolveNextStageFromDecision: GO_BACK_TO_PLOT 返回 plot", () => {
  const result = resolveNextStageFromDecision({ action: 'GO_BACK_TO_PLOT' }, 'writer');
  assert.equal(result, 'plot');
});

// WRITE_ALL_CHAPTERS 動作測試
test("resolveNextStageFromDecision: WRITE_ALL_CHAPTERS 跳轉到 writer", () => {
  const result = resolveNextStageFromDecision({ action: 'WRITE_ALL_CHAPTERS' }, 'worldview');
  assert.equal(result, 'writer');
});

test("resolveNextStageFromDecision: WRITE_ALL_CHAPTERS 從任意階段都到 writer", () => {
  assert.equal(resolveNextStageFromDecision({ action: 'WRITE_ALL_CHAPTERS' }, 'worldview'), 'writer');
  assert.equal(resolveNextStageFromDecision({ action: 'WRITE_ALL_CHAPTERS' }, 'characters'), 'writer');
  assert.equal(resolveNextStageFromDecision({ action: 'WRITE_ALL_CHAPTERS' }, 'plot'), 'writer');
});

// WAIT_USER / FINISH 動作測試
test("resolveNextStageFromDecision: WAIT_USER 返回 null", () => {
  const result = resolveNextStageFromDecision({ action: 'WAIT_USER' }, 'worldview');
  assert.equal(result, null);
});

test("resolveNextStageFromDecision: FINISH 返回 null", () => {
  const result = resolveNextStageFromDecision({ action: 'FINISH' }, 'writer');
  assert.equal(result, null);
});

// 未知 action 測試
test("resolveNextStageFromDecision: 未知 action 返回 null", () => {
  const result = resolveNextStageFromDecision({ action: 'UNKNOWN_ACTION' }, 'worldview');
  assert.equal(result, null);
});

test("resolveNextStageFromDecision: 無 decision 物件返回 null", () => {
  const result = resolveNextStageFromDecision(null, 'worldview');
  assert.equal(result, null);
});

test("resolveNextStageFromDecision: decision 無 action 返回 null", () => {
  const result = resolveNextStageFromDecision({}, 'worldview');
  assert.equal(result, null);
});