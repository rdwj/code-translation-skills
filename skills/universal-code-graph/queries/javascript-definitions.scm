; JavaScript/TypeScript function and class definitions
; Extracts: function_declaration, arrow_function, class_declaration, method_definition

; Function declarations
(function_declaration
  name: (identifier) @name)

; Function declarations with parameters
(function_declaration
  name: (identifier) @name
  parameters: (formal_parameters) @parameters)

; Function declarations with return type (TypeScript)
(function_declaration
  name: (identifier) @name
  return_type: (type_annotation) @return_type)

; Async function declarations
(function_declaration
  "async" @async_keyword
  name: (identifier) @name)

; Generator function declarations
(function_declaration
  "*" @generator_keyword
  name: (identifier) @name)

; Class declarations
(class_declaration
  name: (identifier) @name)

; Class declarations with extends
(class_declaration
  name: (identifier) @name
  superclass: (identifier) @superclass)

; Class declarations with implements (TypeScript)
(class_declaration
  name: (identifier) @name
  implements: (class_heritage) @interfaces)

; Method definitions within classes
(method_definition
  name: (property_identifier) @method_name)

; Constructor method
(method_definition
  name: (property_identifier) @constructor_name
  parameters: (formal_parameters) @parameters)

; Async method definitions
(method_definition
  "async" @async_keyword
  name: (property_identifier) @method_name)

; Arrow function assignments: const func = () => {}
(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: (arrow_function) @arrow_function))

; Function assignments: const func = function() {}
(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: (function_expression
      name: (identifier) @function_name)))

; Function assignments without name: const func = function() {}
(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: (function_expression)))

; Exported function declarations
(export_statement
  (function_declaration
    name: (identifier) @name))

; Exported class declarations
(export_statement
  (class_declaration
    name: (identifier) @name))

; Default export function
(export_statement
  "default" @default_keyword
  (function_declaration
    name: (identifier) @name))

; Getter method
(method_definition
  "get" @getter_keyword
  name: (property_identifier) @property_name)

; Setter method
(method_definition
  "set" @setter_keyword
  name: (property_identifier) @property_name)
