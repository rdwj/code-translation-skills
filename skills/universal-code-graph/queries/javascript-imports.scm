; JavaScript/TypeScript import statements
; Extracts: import_statement, require() calls

; Named imports: import { name } from 'module'
(import_statement
  "import" @import_keyword
  (import_clause
    (named_imports
      (import_specifier
        name: (identifier) @name))))

; Named imports with alias: import { name as alias } from 'module'
(import_statement
  "import" @import_keyword
  (import_clause
    (named_imports
      (import_specifier
        name: (identifier) @name
        "as" @as_keyword
        (identifier) @alias))))

; Default import: import module from 'module'
(import_statement
  "import" @import_keyword
  (import_clause
    (identifier) @default_import)
  "from" @from_keyword
  (string) @module)

; Namespace import: import * as module from 'module'
(import_statement
  "import" @import_keyword
  (import_clause
    (namespace_import
      (identifier) @alias))
  "from" @from_keyword
  (string) @module)

; Combined default and named: import module, { name } from 'module'
(import_statement
  "import" @import_keyword
  (import_clause
    (identifier) @default_import
    "," @comma
    (named_imports
      (import_specifier
        name: (identifier) @named_import))))

; Side-effect imports: import 'module'
(import_statement
  "import" @import_keyword
  (string) @module)

; Require calls: const module = require('module')
(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: (call_expression
      function: (identifier) @require_func
      arguments: (arguments
        (string) @module))))

; Require with destructuring: const { name } = require('module')
(variable_declaration
  (variable_declarator
    name: (object_pattern) @destructure
    value: (call_expression
      function: (identifier) @require_func
      arguments: (arguments
        (string) @module))))

; Dynamic import: import('module')
(call_expression
  function: (identifier) @import_keyword
  arguments: (arguments
    (string) @module))

; Re-export: export { name } from 'module'
(export_statement
  (export_clause
    (export_specifier
      name: (identifier) @name))
  "from" @from_keyword
  (string) @module)

; Re-export all: export * from 'module'
(export_statement
  "*" @export_all
  "from" @from_keyword
  (string) @module)

; Export default: export default import
(export_statement
  "default" @default_keyword
  (identifier) @name)
