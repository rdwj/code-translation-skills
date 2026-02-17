; Python import statements
; Extracts: import_statement, import_from_statement

; Simple import: import module
(import_statement
  "import" @import_keyword
  (dotted_name
    (identifier) @module))

; Simple import with alias: import module as alias
(import_statement
  "import" @import_keyword
  (dotted_name
    (identifier) @module)
  "as" @as_keyword
  (identifier) @alias)

; Multiple imports: import module1, module2
(import_statement
  "import" @import_keyword
  (dotted_name) @module)

; From imports: from module import name
(import_from_statement
  "from" @from_keyword
  module: (dotted_name
    (identifier) @module)
  "import" @import_keyword
  (import_name
    name: (identifier) @name))

; From imports with alias: from module import name as alias
(import_from_statement
  "from" @from_keyword
  module: (dotted_name) @module
  "import" @import_keyword
  (import_name
    name: (identifier) @name
    "as" @as_keyword
    alias: (identifier) @alias))

; From imports with star: from module import *
(import_from_statement
  "from" @from_keyword
  module: (dotted_name) @module
  "import" @import_keyword
  "*" @wildcard)

; From imports without module (relative): from . import name
(import_from_statement
  "from" @from_keyword
  "." @dot
  "import" @import_keyword
  (import_name) @name)

; Relative imports: from ..module import name
(import_from_statement
  "from" @from_keyword
  module: (relative_import) @module
  "import" @import_keyword
  (import_name) @name)
