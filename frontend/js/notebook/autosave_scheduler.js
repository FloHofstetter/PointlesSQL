// Phase 12.7 Sprint 75 — autosave debounce + queue carved out of main.js.
//
// Owns three pieces of state that used to live as plain ``let`` vars
// in the orchestrator: the pending setTimeout handle, an in-flight
// flag, and a queued-while-saving flag.  All three are private to
// this factory's closure — same BUG-64-02 reactivity-boundary
// rationale as createClosureRefs (timer handles parked on Alpine's
// proxy let the reactive deep-walk reach into the timer's captured
// closure on every re-render).
//
// The save() implementation itself stays in main.js because it owns
// the wire-format conversion, fetch, and reactive UI updates.  This
// module owns only the "when do we fire?" + "is one already
// running?" + "should we re-fire after this finishes?" choreography.

export function createAutosaveScheduler({ debounceMs }) {
    let timerHandle = null;
    let inFlight = false;
    let queued = false;
    let currentDebounceMs = debounceMs;

    function schedule(callback) {
        scheduleWith(callback, currentDebounceMs);
    }

    function scheduleWith(callback, ms) {
        if (timerHandle) window.clearTimeout(timerHandle);
        timerHandle = window.setTimeout(() => {
            timerHandle = null;
            callback();
        }, ms);
    }

    function cancel() {
        if (timerHandle) {
            window.clearTimeout(timerHandle);
            timerHandle = null;
        }
    }

    function setDebounceMs(ms) {
        if (Number.isFinite(ms)) currentDebounceMs = ms;
    }

    // beginSave returns false when a save is already running — the
    // caller flips ``queued`` and short-circuits.  Mirrors what the
    // pre-Sprint-75 inline guard did in main.js::save().
    function beginSave() {
        if (inFlight) {
            queued = true;
            return false;
        }
        inFlight = true;
        return true;
    }

    // endSave clears the in-flight flag and re-schedules the supplied
    // callback if anything queued during the run.
    function endSave(rescheduleCallback) {
        inFlight = false;
        if (queued) {
            queued = false;
            schedule(rescheduleCallback);
        }
    }

    return {
        schedule,
        scheduleWith,
        cancel,
        setDebounceMs,
        beginSave,
        endSave,
    };
}
