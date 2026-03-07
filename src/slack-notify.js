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
