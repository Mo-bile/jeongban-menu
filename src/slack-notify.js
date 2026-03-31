/**
 * Slack Incoming Webhook으로 주간 메뉴 알림 메시지를 전송합니다.
 * Block Kit으로 제목, 본문 요약, 시간, 이미지를 구성합니다.
 */

import { IncomingWebhook } from "@slack/webhook";

/**
 * 주간 메뉴 데이터로 Slack Block Kit 메시지를 구성합니다.
 * @param {{ title: string; imageUrl: string; body: string; time: string }} item
 * @returns {Array<object>} Slack blocks
 */
function buildMenuBlocks(item) {
  const blocks = [
    {
      type: "header",
      text: { type: "plain_text", text: "🍽 [정반식당] 주간 메뉴 업데이트", emoji: true },
    },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: `*제목*\n${item.title || "—"}` },
        { type: "mrkdwn", text: `*게시*\n${item.time || "—"}` },
      ],
    },
  ];

  if (item.body) {
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: item.body },
    });
  }

  if (item.imageUrl) {
    blocks.push({
      type: "image",
      image_url: item.imageUrl,
      alt_text: item.title || "주간 메뉴표",
    });
  }

  blocks.push({
    type: "context",
    elements: [
      {
        type: "mrkdwn",
        text: "<https://map.naver.com/p/entry/place/1671594903?placePath=%2Ffeed|네이버 지도에서 보기>",
      },
    ],
  });

  return blocks;
}

/**
 * Slack Incoming Webhook으로 주간 메뉴 알림을 보냅니다.
 * @param {string} webhookUrl - Slack Incoming Webhook URL
 * @param {{ title: string; imageUrl: string; body: string; time: string }} item - 파싱된 피드 항목
 * @returns {Promise<void>}
 */
export async function sendMenuNotification(webhookUrl, item) {
  const webhook = new IncomingWebhook(webhookUrl);
  const blocks = buildMenuBlocks(item);

  await webhook.send({
    text: `[정반식당] ${item.title || "주간 메뉴"} — ${item.time || ""}`,
    blocks,
  });
}

/**
 * OCR로 추출한 오늘의 메뉴 데이터로 Slack Block Kit 메시지를 구성합니다.
 * @param {{ weekday: string; menu: string[] }} ocrData
 * @returns {Array<object>} Slack blocks
 */
function buildMenuTextBlocks(ocrData) {
  const todayKst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const month = todayKst.getUTCMonth() + 1;
  const day = todayKst.getUTCDate();

  const special = ocrData.special ? `\`${ocrData.special}\`` : null;
  const menuText = [special, ...ocrData.menu].filter(Boolean).join("\n");

  return [
    {
      type: "header",
      text: {
        type: "plain_text",
        text: `🍽 [정반식당] 오늘의 메뉴 (${month}/${day} ${ocrData.weekday})`,
        emoji: true,
      },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: menuText },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: "<https://map.naver.com/p/entry/place/1671594903?placePath=%2Ffeed|네이버 지도에서 보기>",
        },
      ],
    },
  ];
}

/**
 * Slack Incoming Webhook으로 OCR 추출 텍스트 기반 오늘의 메뉴 알림을 보냅니다.
 * OCR 실패 또는 공휴일 케이스는 호출 전에 걸러져야 합니다.
 * @param {string} webhookUrl - Slack Incoming Webhook URL
 * @param {{ weekday: string; menu: string[] }} ocrData - OCR 결과
 * @returns {Promise<void>}
 */
export async function sendMenuTextNotification(webhookUrl, ocrData) {
  const webhook = new IncomingWebhook(webhookUrl);
  const blocks = buildMenuTextBlocks(ocrData);

  await webhook.send({
    text: `[정반식당] ${ocrData.weekday}요일 메뉴`,
    blocks,
  });
}
