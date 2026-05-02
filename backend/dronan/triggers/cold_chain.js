/**
 * Atlas Trigger: cold_chain
 *
 * Watches ``telemetry`` for cold-chain bag temperature breaches and
 * forwards them to /internal/cold_chain_breach.
 */
exports = async function (changeEvent) {
  const t = changeEvent.fullDocument || {};
  const temp = t?.cold_chain?.bag_temp_c;
  if (typeof temp !== "number" || temp <= 6.0) {
    return { skipped: true };
  }

  const apiUrl = context.values.get("DRONAN_API_URL") || "";
  const apiKey = context.values.get("DRONAN_API_KEY") || "";

  const res = await context.http.post({
    url: `${apiUrl}/internal/cold_chain_breach`,
    headers: {
      "Content-Type": ["application/json"],
      "X-Internal-Key": [apiKey],
    },
    body: JSON.stringify({
      mission_id: t.mission_id,
      bag_temp_c: temp,
      threshold_c: 6.0,
    }),
    encodeBodyAsJSON: false,
  });
  return { mission_id: t.mission_id, status: res.statusCode };
};
