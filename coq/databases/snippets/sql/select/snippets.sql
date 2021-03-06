SELECT
  snippets.grammar AS grammar,
  matches.match    AS prefix,
  snippets.content AS snippet,
  snippets.label   AS label,
  snippets.doc     AS doc
FROM snippets
JOIN matches
ON matches.snippet_id = snippets.rowid
JOIN extensions_view
ON
  snippets.filetype = extensions_view.dest
WHERE
  :word <> ''
  AND
  extensions_view.src = :filetype
  AND
  matches.lmatch LIKE X_LIKE_ESC(SUBSTR(LOWER(:word), 1, :exact)) ESCAPE '!'
  AND
  X_SIMILARITY(LOWER(:word), matches.lmatch, :look_ahead) > :cut_off
GROUP BY
  snippets.rowid
LIMIT :limit
