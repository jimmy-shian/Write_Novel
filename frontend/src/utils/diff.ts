/**
 * Clean Line-based Diff Algorithm (LCS / Myers based)
 * Zero external dependencies. Strictly compliant with Clean-Room specification.
 */

export interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  text: string;
  originalLine?: number;
  proposedLine?: number;
}

export interface DiffSummary {
  addedCount: number;
  removedCount: number;
  unchangedCount: number;
  lines: DiffLine[];
}

export function computeLineDiff(original: string, proposed: string): DiffSummary {
  const origLines = original ? original.split('\n') : [];
  const propLines = proposed ? proposed.split('\n') : [];

  const m = origLines.length;
  const n = propLines.length;

  // LCS dynamic programming table (matrix)
  // For practical performance on standard chapter lengths (~1000 lines),
  // we compute LCS on lines.
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));

  for (let i = 0; i < m; i++) {
    for (let j = 0; j < n; j++) {
      if (origLines[i] === propLines[j]) {
        dp[i + 1][j + 1] = dp[i][j] + 1;
      } else {
        dp[i + 1][j + 1] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  // Backtrack to construct diff
  let i = m;
  let j = n;
  const reversedDiff: DiffLine[] = [];

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && origLines[i - 1] === propLines[j - 1]) {
      reversedDiff.push({
        type: 'unchanged',
        text: origLines[i - 1],
        originalLine: i,
        proposedLine: j,
      });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      reversedDiff.push({
        type: 'added',
        text: propLines[j - 1],
        proposedLine: j,
      });
      j--;
    } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
      reversedDiff.push({
        type: 'removed',
        text: origLines[i - 1],
        originalLine: i,
      });
      i--;
    }
  }

  const lines = reversedDiff.reverse();

  let addedCount = 0;
  let removedCount = 0;
  let unchangedCount = 0;

  for (const line of lines) {
    if (line.type === 'added') addedCount++;
    else if (line.type === 'removed') removedCount++;
    else unchangedCount++;
  }

  return {
    addedCount,
    removedCount,
    unchangedCount,
    lines,
  };
}
