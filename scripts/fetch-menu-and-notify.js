#!/usr/bin/env node
/**
 * 진입점: 네이버 지도에서 최신 주간메뉴표(첫 번째 피드)를 가져와 Slack으로 알림을 보냅니다.
 * 매주 cron 또는 GitHub Actions 등으로 실행하는 것을 권장합니다.
 *
 * 사용법:
 *   SLACK_WEBHOOK_URL=xxx node scripts/fetch-menu-and-notify.js
 *   또는 .env에 SLACK_WEBHOOK_URL 설정 후: npm run fetch-menu
 */

import "dotenv/config";
import { fetchLatestFeedItem } from "../src/naver-feed.js";
import { sendMenuNotification } from "../src/slack-notify.js";

const SLACK_WEBHOOK_URL = process.env.SLACK_WEBHOOK_URL;

async function main() {
  if (!SLACK_WEBHOOK_URL) {
    console.error("환경 변수 SLACK_WEBHOOK_URL이 필요합니다. .env 또는 셸에서 설정하세요.");
    process.exit(1);
  }

  console.log("네이버 지도 피드에서 최신 주간메뉴표 수집 중...");

  let item;
  try {
    item = await fetchLatestFeedItem({
      timeout: 15000,
      headless: true,
    });
  } catch (err) {
    console.error("피드 수집 실패:", err.message);
    process.exit(1);
  }

  if (!item || (!item.title && !item.imageUrl)) {
    console.error("수집된 피드 항목이 없거나 필수 필드가 비어 있습니다.");
    process.exit(1);
  }

  console.log("수집 완료:", item.title || "(제목 없음)", "|", item.time || "");

  try {
    await sendMenuNotification(SLACK_WEBHOOK_URL, item);
    console.log("Slack 알림 전송 완료.");
  } catch (err) {
    console.error("Slack 전송 실패:", err.message);
    process.exit(1);
  }
}

main();
