#!/usr/bin/env node
/**
 * 진입점: 네이버 지도에서 최신 주간메뉴표 이미지를 가져와
 * Python Surya OCR로 오늘의 메뉴를 추출한 후 Slack으로 알림을 보냅니다.
 *
 * 평일 매일 실행 (GitHub Actions cron: "10 1 * * 1-5")
 * OCR 실패 또는 공휴일 감지 시 Slack 전송하지 않습니다.
 *
 * 사용법:
 *   SLACK_WEBHOOK_URL=xxx node scripts/fetch-menu-ocr-and-notify.js
 *   또는 .env에 SLACK_WEBHOOK_URL 설정 후: npm run fetch-menu-ocr
 */

import "dotenv/config";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fetchLatestFeedItem } from "../src/naver-feed.js";
import { sendMenuTextNotification } from "../src/slack-notify.js";

const execFileAsync = promisify(execFile);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const SLACK_WEBHOOK_URL = process.env.SLACK_WEBHOOK_URL;
const PYTHON_BIN = process.env.PYTHON_BIN || "python3";
const OCR_SCRIPT = path.resolve(__dirname, "ocr-menu.py");

async function runOcr(imageUrl) {
  const env = { ...process.env };
  if (process.env.FORCE_WEEKDAY !== undefined) env.FORCE_WEEKDAY = process.env.FORCE_WEEKDAY;

  const { stdout } = await execFileAsync(PYTHON_BIN, [OCR_SCRIPT, imageUrl], {
    timeout: 300_000,
    maxBuffer: 1024 * 1024,
    env,
  });
  // Surya 모델 로딩 시 warning이 stdout에 섞일 수 있으므로 마지막 JSON 라인만 파싱
  const lastJsonLine = stdout
    .trim()
    .split("\n")
    .findLast((l) => l.trimStart().startsWith("{"));
  if (!lastJsonLine) throw new Error("OCR stdout에서 JSON을 찾을 수 없습니다.");
  return JSON.parse(lastJsonLine);
}

async function main() {
  if (!SLACK_WEBHOOK_URL) {
    console.error("환경 변수 SLACK_WEBHOOK_URL이 필요합니다.");
    process.exit(1);
  }

  console.log("네이버 지도 피드에서 최신 주간메뉴표 수집 중...");

  let item;
  try {
    item = await fetchLatestFeedItem({ timeout: 15000, headless: true });
  } catch (err) {
    console.error("피드 수집 실패:", err.message);
    process.exit(1);
  }

  if (!item?.imageUrl) {
    console.error("이미지 URL을 찾을 수 없습니다.");
    process.exit(1);
  }

  console.log("이미지 URL:", item.imageUrl);
  console.log("OCR 실행 중...");

  let ocrResult;
  try {
    ocrResult = await runOcr(item.imageUrl);
  } catch (err) {
    console.error("OCR 실패 (전송 생략):", err.message);
    process.exit(0);
  }

  if (!ocrResult.success) {
    console.error("OCR 결과 오류 (전송 생략):", ocrResult.error);
    process.exit(0);
  }

  if (ocrResult.is_holiday) {
    console.log(`[${ocrResult.weekday}] 공휴일 감지 → 전송 생략 (${ocrResult.reason})`);
    process.exit(0);
  }

  if (!ocrResult.menu || ocrResult.menu.length === 0) {
    console.error("메뉴 추출 결과가 비어 있습니다 (전송 생략).");
    process.exit(0);
  }

  console.log(`[${ocrResult.weekday}] 메뉴 ${ocrResult.menu.length}개 추출 완료`);

  try {
    await sendMenuTextNotification(SLACK_WEBHOOK_URL, ocrResult);
    console.log("Slack 알림 전송 완료.");
  } catch (err) {
    console.error("Slack 전송 실패:", err.message);
    process.exit(1);
  }
}

main();
