# Data Product Event Port — B1/D1 Delta CDF + WS / HTTP fan-out

> **Mode:** `hybrid` · **Surface:** Overview Event-stream card + `GET /api/data-products/{c}/{s}/events` (chunked NDJSON) + `WS /ws/data-products/{c}/{s}/events` + subscription CRUD + scheduler `event_port_pump`

Walks an operator through declaring an event output port on a
product, subscribing a downstream consumer, pumping rows through
the in-process WS hub, and confirming the durable cursor advances.

## Preconditions

* PointlesSQL running with the event port enabled:
  ```bash
  POINTLESSQL_EVENT_PORT_ENABLED=true uv run pointlessql
  ```
* Loaded product `main.events_gold` with a Delta-CDF-enabled table
  `events_gold.events`.
* An `event`-kind output port declared on the product (Overview →
  Ports → "Add output port", `kind=event`, `format=ndjson`).

## Browser flow

| Step | Expect |
|---|---|
| Open `/data-products/main/events_gold` → Overview | Event-stream card renders; badge `declared`; "Subscribers (0)" |
| Open the "Connect (curl / WebSocket)" `<details>` | curl + JS snippets render with the product's URL filled in |
| Fill the subscribe form: table `events`, label `fraud-pipeline`, Subscribe | New row in the Subscriptions table: status `active`, cursor `v0` |
| In a separate shell: `pql.write_table(...)` against `main.events_gold.events` | Delta version increments |
| Wait one scheduler tick (≤5s) | Subscription cursor advances; `event_port_pump` log entry appears |
| Run the curl snippet | NDJSON rows stream from `since=0` and the stream completes |
| Click **Pause** on the subscription | Status `paused`; pump skips this subscription on the next tick |
| Click **Resume** | Status `active`; pump catches up |
| Click **Rewind** with `to_version=0` (steward only) | Cursor moves back; next pump re-delivers since v0 |

## WebSocket smoke

```js
const ws = new WebSocket(
  "ws://localhost:8000/ws/data-products/main/events_gold/events?table=events"
);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

The first frame is `{hello:true, product, table}`; subsequent frames
carry `{version, commit_timestamp, change_type, data}`.

## Agent flow (Hermes)

```python
client.subscribe_data_product_event_port(
    catalog="main", schema="events_gold",
    table="events", consumer_label="fraud-pipeline",
)

# One-shot pull (no WS — for batch agents):
client.read_data_product_event_port(
    catalog="main", schema="events_gold", table="events", since=0
)

# Steward / admin control:
client.control_event_subscription(
    catalog="main", schema="events_gold",
    subscription_id=1, action="rewind", to_version=0,
)
```

## Common issues

* **Empty stream** — CDF must be enabled on the underlying Delta
  table.  The write path stamps `delta.enableChangeDataFeed=true` on
  first write of a managed product table.
* **Cursor not advancing** — confirm the scheduler is running and
  `POINTLESSQL_EVENT_PORT_ENABLED=true`; the executor is
  default-off otherwise.
* **WS disconnects immediately** — the WS endpoint expects no
  inbound payload; sending data to it triggers nothing but the
  client reads will continue.
