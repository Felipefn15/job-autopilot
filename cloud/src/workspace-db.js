// D1-shaped adapter for a user's physically separate SQLite Durable Object database.
export function workspaceDB(storage) {
  return {
    prepare(sql) {
      let args = [];
      const execute = () => {
        const cursor = storage.sql.exec(sql, ...args);
        const results = cursor.toArray();
        return {
          results,
          success: true,
          meta: { changes: storage.sql.exec("SELECT changes() AS n").one().n },
        };
      };
      return {
        bind(...values) {
          args = values;
          return this;
        },
        async first(column) {
          const row = execute().results[0] || null;
          return column ? (row?.[column] ?? null) : row;
        },
        async all() {
          return execute();
        },
        async run() {
          return execute();
        },
        _run: execute,
      };
    },
    async batch(statements) {
      return storage.transactionSync(() => statements.map((s) => s._run()));
    },
  };
}
