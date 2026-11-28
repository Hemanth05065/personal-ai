// node --test apps/web/src/sources.test.mjs
import assert from "node:assert/strict";
import test from "node:test";

import { splitSources } from "./sources.js";

test("the server's sources line becomes chips, and leaves the answer", () => {
  const text = "GTA 6 comes out on 19 November 2026.\n\nSources: [Rockstar Games](https://www.rockstargames.com/VI) · [IGN](https://ign.com/gta)";
  assert.deepEqual(splitSources(text), {
    body: "GTA 6 comes out on 19 November 2026.",
    sources: [
      { title: "Rockstar Games", url: "https://www.rockstargames.com/VI", host: "rockstargames.com" },
      { title: "IGN", url: "https://ign.com/gta", host: "ign.com" },
    ],
  });
});

test("text without a sources line is unchanged", () => {
  assert.deepEqual(splitSources("Hello."), { body: "Hello.", sources: [] });
  assert.deepEqual(splitSources(""), { body: "", sources: [] });
});

test("only a last line counts, and only real links", () => {
  const middle = "Sources: [A](https://a.example/)\nMore text after it.";
  assert.equal(splitSources(middle).sources.length, 0);
  assert.deepEqual(splitSources("Sources: none found"), { body: "Sources: none found", sources: [] });
  assert.equal(splitSources("Sources: [x](javascript:alert(1))").sources.length, 0);
});

test("a sources line alone still parses", () => {
  const { body, sources } = splitSources("Sources: [Page](https://example.org/p)");
  assert.equal(body, "");
  assert.equal(sources[0].host, "example.org");
});
