// Contract-Tests tab on the data-product page.
//
// Exports: dataProductContractTests — list + declare + run + fixtures.

function dpBase(catalog, schema) {
  return '/api/data-products/' + encodeURIComponent(catalog) + '/' + encodeURIComponent(schema);
}

export function dataProductContractTests(catalog, schema, canManage) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: !!canManage,
    loaded: false,
    error: '',
    tests: [],
    fixtures: [],
    runMode: 'synthetic',
    running: false,
    outcome: null,
    newTest: {
      name: '',
      assertion_kind: 'row_count_range',
      assertion_spec_json: '',
      severity: 'warn',
    },

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const [testsRes, fixturesRes] = await Promise.all([
          fetch(dpBase(this.catalog, this.schema) + '/contract-tests'),
          fetch(dpBase(this.catalog, this.schema) + '/fixtures'),
        ]);
        if (testsRes.ok) {
          const data = await testsRes.json();
          this.tests = data.tests || data.contract_tests || [];
        }
        if (fixturesRes.ok) {
          const data = await fixturesRes.json();
          this.fixtures = data.fixtures || [];
        }
        this.loaded = true;
      } catch (e) {
        this.error = 'Failed to load contract tests: ' + e.message;
      }
    },

    async declareTest() {
      this.error = '';
      const body = {
        name: this.newTest.name.trim(),
        assertion_kind: this.newTest.assertion_kind,
        severity: this.newTest.severity,
      };
      const specRaw = this.newTest.assertion_spec_json.trim();
      if (specRaw) {
        try {
          body.assertion_spec = JSON.parse(specRaw);
        } catch (e) {
          this.error = 'assertion_spec JSON invalid: ' + e.message;
          return;
        }
      }
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/contract-tests', {
        method: 'POST',
        body: body,
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to declare';
        return;
      }
      this.newTest.name = '';
      this.newTest.assertion_spec_json = '';
      await this.reload();
    },

    async removeTest(id) {
      if (!window.confirm('Delete this contract test?')) return;
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/contract-tests/' + id,
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.reload();
    },

    async removeFixture(id) {
      if (!window.confirm('Remove this fixture?')) return;
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/fixtures/' + id, {
        method: 'DELETE',
      });
      if (!res.ok) return;
      await this.reload();
    },

    async runAll() {
      this.error = '';
      this.running = true;
      this.outcome = null;
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/contract-tests/run?mode=' + this.runMode,
        { method: 'POST' }
      );
      this.running = false;
      if (!res.ok) {
        this.error = res.error || 'Run failed';
        return;
      }
      this.outcome = res.data || null;
    },
  };
}
