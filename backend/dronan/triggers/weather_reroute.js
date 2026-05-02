/**
 * Atlas Trigger: weather_reroute
 *
 * Fires when ``weather_observations`` receives a new doc whose
 * ``classification`` is "no-go" or "degraded". POSTs to the backend's
 * /internal/replan endpoint so the supervisor can re-route any active
 * missions whose corridor passes through the affected location.
 *
 * Configuration (deployed via `scripts/deploy_triggers.sh`):
 *   - Trigger type: Database
 *   - Operation:    Insert
 *   - Collection:   weather_observations
 *   - Function:     this file
 *
 * Environment:
 *   DRONAN_API_URL — base URL of the FastAPI backend.
 *   DRONAN_API_KEY — shared secret for the /internal/* endpoints.
 */
exports = async function (changeEvent) {
  const obs = changeEvent.fullDocument || {};
  if (!obs || (obs.classification !== "no-go" && obs.classification !== "degraded")) {
    return { skipped: true };
  }

  const db = context.services.get("mongodb-atlas").db("dronan");

  // Find active missions whose plan touches this location.
  const missions = await db
    .collection("missions")
    .find({
      status: { $in: ["planned", "executing"] },
      $or: [{ depot: obs.location_id }, { stops: obs.location_id }],
    })
    .toArray();

  const apiUrl = context.values.get("DRONAN_API_URL") || "";
  const apiKey = context.values.get("DRONAN_API_KEY") || "";

  const results = [];
  for (const m of missions) {
    const res = await context.http.post({
      url: `${apiUrl}/internal/replan`,
      headers: {
        "Content-Type": ["application/json"],
        "X-Internal-Key": [apiKey],
      },
      body: JSON.stringify({
        mission_id: m._id,
        reason: `weather_${obs.classification}`,
      }),
      encodeBodyAsJSON: false,
    });
    results.push({ mission_id: m._id, status: res.statusCode });
  }
  return { dispatched: results.length, results };
};
