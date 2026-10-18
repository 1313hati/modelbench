Write `justify(words, width)` in Python, returning a list of lines that fully
justify the text, exactly like a newspaper column.

Rules:
- Pack as many whole words as possible into each line, in order. Do not split words.
- A line with two or more words is fully justified: spaces between words are
  increased so the line is exactly `width` characters. Extra spaces are
  distributed left to right: if 7 spaces must be spread over 3 gaps, the gaps
  get 3, 2, 2.
- The last line is left-justified: words joined by one space, no trailing spaces.
- A line containing one word is left-justified.
- `width` must be an integer >= 1, else raise `ValueError`.
- Every word must be a non-empty string without whitespace and no longer than
  `width`; otherwise raise `ValueError`.
- `justify([], 10)` returns `[]`.

Example, width 16:
`["This", "is", "an", "example", "of", "text", "justification."]` becomes
`["This    is    an", "example  of text", "justification."]`

Return the complete file. Standard library only.
