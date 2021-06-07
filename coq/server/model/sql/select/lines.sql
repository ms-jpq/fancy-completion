SELECT
  line
FROM lines
WHERE
  buffer = :buffer
  AND
  line_num >= :lo
  AND
  CASE
    WHEN :hi > 0 THEN line_num < :hi
    ELSE TRUE
  END