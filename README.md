# gql-suggest

**Enumerate GraphQL schemas on servers with introspection disabled.**

Apollo Server's `introspection: false` hides the schema — but unless field
suggestions are also disabled, validation errors leak real field names within
edit distance of any probe. This tool mines those suggestions breadth-first
and reconstructs a usable schema map.

## Why it works

```
{"errors":[{"message":"Cannot query field \"usr\" on type \"Query\".
 Did you mean \"user\" or \"users\"?"}]}
```

Every probe yields up to ~5 near-miss names. Feed candidates in, walk the
graph out: root fields, then subfields, then their subfields.

## Safe by construction

- only well-formed queries are sent
- no mutations, no introspection fields, no batching, no aliases abuse
- the server does all the leaking — the tool just reads validation errors

## Usage

```
python3 gql_suggest.py https://target/graphql --depth 1
python3 gql_suggest.py https://target/graphql --wordlist words.txt --depth 2
python3 gql_suggest.py https://target/graphql --header "Authorization: Bearer ey..."
```

Flags: `--depth` BFS depth below root fields · `--delay` request pacing ·
`--wordlist` custom candidate list · `--header` auth headers

## Notes for defenders

Disable suggestions too:

```js
const server = new ApolloServer({
  introspection: false,
  fieldResolverLevelHints: 'off', // see Apollo docs: formatError minify
});
```

(Practically: strip `Did you mean` from errors in production — that is the
entire leak.)

## Status

- root-field mining: working
- subfield walk: working (depth-limited)
- websocket subscription surface: planned

## License

MIT
