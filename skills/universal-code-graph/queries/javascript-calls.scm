; JavaScript/TypeScript function and method calls
; Extracts: call_expression nodes with function names and attribute access chains

; Simple function call: func()
(call_expression
  function: (identifier) @name)

; Method call: obj.method()
(call_expression
  function: (member_expression
    object: (identifier) @object
    property: (identifier) @method))

; Chained method calls: obj.method1().method2()
(call_expression
  function: (member_expression
    object: (call_expression) @chained_call
    property: (identifier) @method))

; Nested member access: obj.attr1.attr2()
(call_expression
  function: (member_expression
    object: (member_expression
      object: (identifier) @object
      property: (identifier) @attr1)
    property: (identifier) @attr2))

; Subscript access method calls: obj[key].method()
(call_expression
  function: (member_expression
    object: (subscript_expression) @subscript_obj
    property: (identifier) @method))

; Constructor calls: new ClassName()
(new_expression
  constructor: (identifier) @constructor_name)

; Calls with arguments
(call_expression
  function: (identifier) @name
  arguments: (arguments) @arguments)

; Built-in calls like console.log()
(call_expression
  function: (member_expression
    object: (identifier) @object
    property: (identifier) @method)
  arguments: (arguments) @arguments)

; Method calls on this: this.method()
(call_expression
  function: (member_expression
    object: (this) @this_keyword
    property: (identifier) @method))

; Method calls on super: super.method()
(call_expression
  function: (member_expression
    object: (super) @super_keyword
    property: (identifier) @method))

; Arrow function calls: (() => {})()
(call_expression
  function: (arrow_function) @arrow_function)

; Function expression calls: (function() {})()
(call_expression
  function: (function_expression) @function_expression)

; Optional chaining: obj?.method()
(call_expression
  function: (member_expression
    "?." @optional_chain
    property: (identifier) @method))

; Computed property access: obj[func()]()
(call_expression
  function: (member_expression
    object: (identifier) @object
    property: (computed_property_name) @computed_property))

; Await on call expression: await func()
(await_expression
  (call_expression
    function: (identifier) @name))

; Spread operator in arguments: func(...args)
(call_expression
  function: (identifier) @name
  arguments: (arguments
    (spread_element) @spread))
