# parser_lark.py (Corrigido erro de sintaxe na gramática)
import ast_nodes as ast
import traceback
from lark import Lark, Transformer, Tree, v_args, Token, exceptions
from typing import List, Union, Optional, Tuple
from semantic_analyzer import analyze_semantics
from codegen_llvm import generate_llvm_ir

# --- Gramática (v0.2 - Sem Precedência, Else Simplificado, Comentários //) ---
atom_v02_grammar = r"""
    ?start: program
    program: top_level_item* -> mk_program

    // ----- Top-Level Items -----
    ?top_level_item: extern_block | func_def | const_def | struct_def | enum_def | import_decl

    // --- Declarations ---
    import_decl: KW_IMPORT STRING_LITERAL ";" -> mk_import_decl
    const_def: KW_CONST identifier ":" type "=" expression ";" -> mk_const_def
    struct_def: KW_STRUCT identifier struct_field_def* KW_END -> mk_struct_def
    struct_field_def: identifier ":" type COMMA? -> mk_struct_field_def
    enum_def: KW_ENUM identifier enum_variant_def* KW_END -> mk_enum_def
    enum_variant_def: identifier COMMA? -> mk_enum_variant_def
    extern_block: KW_EXTERN abi_string func_decl* KW_END -> mk_extern_block
    abi_string: STRING_LITERAL
    func_decl: KW_FUNC identifier LPAREN param_list_for_decl RPAREN ARROW type SEMICOLON -> mk_func_decl // Usa lista direta
    param_list_for_decl: [type (COMMA type)* [COMMA VARARGS]] -> process_decl_params // 0 ou mais tipos, opcionalmente com ...
                      | VARARGS -> handle_varargs_only       // Apenas ...
                      | -> empty_param_list // Caso sem parâmetros e sem VARARGS
    func_def: KW_FUNC identifier LPAREN [def_param_list] RPAREN ARROW type statement* KW_END -> mk_func_def // Func body can be empty
    ?def_param_list: parameter (COMMA parameter)*
    parameter: identifier ":" type -> mk_parameter

    // ----- Statements -----
    ?statement: let_binding
              | mut_binding
              | assignment
              | if_stmt
              | while_stmt
              | loop_stmt
              | mem_block
              | e_mem_block
              | return_stmt
              | break_stmt
              | continue_stmt
              | expr_statement

    expr_statement: expression ";" -> mk_expr_statement
    let_binding: KW_LET identifier (":" type)? "=" expression ";" -> mk_let_binding
    mut_binding: MUT identifier (":" type)? "=" expression ";" -> mk_mut_binding
    assignment: lvalue EQ expression ";" -> mk_assignment
    lvalue: postfix_expr
    return_stmt: KW_RETURN expression? ";" -> mk_return_stmt
    break_stmt: KW_BREAK ";" -> mk_break_stmt
    continue_stmt: KW_CONTINUE ";" -> mk_continue_stmt
    if_stmt: KW_IF expression statement* [else_clause] KW_END -> mk_if_stmt
    ?else_clause: KW_ELSE if_stmt          // else if ...
                | KW_ELSE statement*       // else ... (sem end proprio)
    while_stmt: KW_WHILE expression statement* KW_END -> mk_while_stmt
    loop_stmt: KW_LOOP statement* KW_END -> mk_loop_stmt
    mem_block: KW_MEM statement* KW_END -> mk_mem_block
    e_mem_block: KW_E_MEM statement* KW_END -> mk_e_mem_block

    // ----- Tipos -----
    ?type: complex_type | simple_type | function_type_syntax // Adiciona tipo função
    ?complex_type: reference_type | slice_type | pointer_type | array_type
    ?simple_type: unit_type | primitive_or_custom
    primitive_or_custom: identifier -> mk_custom_or_primitive_type
    unit_type: LPAREN RPAREN -> mk_unit_type
    pointer_type: STAR MUT_OR_CONST type -> mk_pointer_type     // Usa STAR normal
    reference_type: AMPERSAND MUT? type -> mk_reference_type // Usa AMPERSAND normal
    slice_type: AMPERSAND MUT? LBRACKET type RBRACKET -> mk_slice_type // Usa AMPERSAND normal
    array_type: LBRACKET type SEMICOLON expression RBRACKET -> mk_array_type
    function_type_syntax: KW_FUNC LPAREN [type_list] RPAREN ARROW type -> mk_function_type
    ?type_list: type (COMMA type)* // Lista de tipos para parâmetros

    // ----- Expressões (Hierarquia define precedência implícita para Earley) -----
    expression: logical_or_expr

    ?logical_or_expr: logical_and_expr (OROR logical_and_expr)*      -> bin_op_expr
    ?logical_and_expr: bitwise_or_expr (ANDAND bitwise_or_expr)*      -> bin_op_expr // Antes: equality_expr
    ?bitwise_or_expr: bitwise_xor_expr (PIPE bitwise_xor_expr)*       -> bin_op_expr // Novo nível |
    ?bitwise_xor_expr: bitwise_and_expr (CARET bitwise_and_expr)*    -> bin_op_expr // Novo nível ^
    ?bitwise_and_expr: equality_expr (AMPERSAND equality_expr)*      -> bin_op_expr // Novo nível & (usa AMPERSAND normal)
    ?equality_expr: comparison_expr ((EQEQ | NE) comparison_expr)*   -> bin_op_expr
    ?comparison_expr: shift_expr ((LT | GT | LE | GE) shift_expr)* -> bin_op_expr // Antes: additive_expr
    ?shift_expr: additive_expr ((LSHIFT | RSHIFT) additive_expr)*   -> bin_op_expr // Novo nível <<, >>
    ?additive_expr: multiplicative_expr ((PLUS | MINUS) multiplicative_expr)* -> bin_op_expr
    ?multiplicative_expr: cast_expr ((STAR | SLASH | PERCENT) cast_expr)* -> bin_op_expr

    ?cast_expr: unary_expr (KW_AS type)? -> mk_cast_expr

    // Usa tokens normais (MINUS, STAR, AMPERSAND) para unários
       ?unary_expr: (BANG | MINUS | STAR | AMPERSAND MUT? | TILDE) unary_expr -> mk_unary_op // Adiciona ~
               | postfix_expr

    ?postfix_expr: primary_expr ( call_suffix | index_suffix | field_suffix )* -> postfix_expr

    ?primary_expr: literal
                 | identifier
                 | grouped_expression
                 | array_literal
                 | struct_literal
                 | namespace_access
                 | underscore_expr
                 | array_repeat_expr

    call_suffix: LPAREN [arg_list] RPAREN -> mk_call_suffix
    index_suffix: LBRACKET expression RBRACKET -> mk_index_suffix
    field_suffix: DOT identifier -> mk_field_suffix
    ?arg_list: expression (COMMA expression)*
    grouped_expression: LPAREN expression RPAREN // Sem alias, transformer padrão deve funcionar
    ?literal: INTEGER_LITERAL -> mk_integer_literal | STRING_LITERAL -> mk_string_literal | BYTE_STRING_LITERAL -> mk_bytestring_literal | CHAR_LITERAL -> mk_char_literal | TRUE -> mk_bool_literal_true | FALSE -> mk_bool_literal_false

    struct_literal: identifier LBRACE [struct_literal_field_list] RBRACE -> mk_struct_literal
    ?struct_literal_field_list: struct_literal_field (COMMA struct_literal_field)* COMMA?
    struct_literal_field: identifier COLON expression -> mk_struct_literal_field
    array_literal: LBRACKET [array_element_list] RBRACKET -> mk_array_literal
    ?array_element_list: expression (COMMA expression)* COMMA?
    array_repeat_expr: LBRACKET expression SEMICOLON expression RBRACKET -> mk_array_repeat_expr
    namespace_access: identifier COLONCOLON identifier -> mk_namespace_access
    underscore_expr: UNDERSCORE -> mk_underscore

    identifier: CNAME -> mk_identifier

    // ----- Terminais -----
    %import common.CNAME             -> CNAME
	STRING_LITERAL: /"([^\\"]|\\.)*"/
    HEX_INTEGER: /0[xX][0-9a-fA-F](_?[0-9a-fA-F])*/
    OCT_INTEGER: /0[oO][0-7](_?[0-7])*/
    BIN_INTEGER: /0[bB][01](_?[01])*/
    DEC_INTEGER: /[1-9](_?[0-9])*|0/ // Decimal: 0 ou começa com 1-9
    INTEGER_LITERAL: HEX_INTEGER | OCT_INTEGER | BIN_INTEGER | DEC_INTEGER // Combina todos
    %import common.WS_INLINE         -> _WS_INLINE
    %import common.CPP_COMMENT       -> _CPP_COMMENT      // Define //
    %import common.SH_COMMENT        -> _SH_COMMENT       // Define #
    %import common.NEWLINE           -> _NEWLINE
    BYTE_STRING_LITERAL: /b"(\\.|[^\\"])*"/
    CHAR_LITERAL: /'(\\.|[^\\'])'/
    MULTILINE_COMMENT: /"{3}[^"]*("+"?[^"]+)*"{3}"/ // Define ""'...'""
    %ignore _WS_INLINE
    %ignore _CPP_COMMENT      // Ignora //
    %ignore _SH_COMMENT       // Ignora #
    %ignore MULTILINE_COMMENT // Ignora ""'..'""
    %ignore _NEWLINE

    // --- Keywords (Separate Lines) ---
    KW_END: "end"
    KW_IMPORT: "import"
    KW_CONST: "const"
    KW_STRUCT: "struct"
    KW_ENUM: "enum"
    KW_EXTERN: "extern"
    KW_FUNC: "func"
    KW_LET: "let"
    MUT: "mut"
    KW_RETURN: "return"
    KW_BREAK: "break"
    KW_CONTINUE: "continue"
    KW_IF: "if"
    KW_WHILE: "while"
    KW_LOOP: "loop"
    KW_MEM: "mem"
    KW_E_MEM: "e_mem"
    KW_ELSE: "else"
    KW_AS: "as"
    TRUE: "true"
    FALSE: "false"

    // --- Operators & Delimiters (Separate Lines) ---
    BANG: "!"
    TILDE: "~"  // Novo operador unário
    COLON: ":"
    SEMICOLON: ";"
    LPAREN: "("
    RPAREN: ")"
    LBRACE: "{"
    RBRACE: "}"
    LBRACKET: "["
    RBRACKET: "]"
    ARROW: "->"
    DOT: "."
    COLONCOLON: "::"
    COMMA: ","
    VARARGS: "..."
    EQEQ: "=="
    EQ: "="
    NE: "!="
    LT: "<"
    GT: ">"
    LE: "<="
    GE: ">="
    PLUS: "+"
    MINUS: "-"  // Token único
    STAR: "*"   // Token único
    AMPERSAND: "&" // Token único
    SLASH: "/"
    PERCENT: "%"
    PIPE: "|"      // Novo operador binário
    CARET: "^"     // Novo operador binário
    LSHIFT: "<<"   // Novo operador binário
    RSHIFT: ">>"   // Novo operador binário
    ANDAND: "&&"
    OROR: "||"
    UNDERSCORE: "_"

    // Helper for PointerType
    MUT_OR_CONST: "const" | "mut"

    // --- REMOVIDO: Precedência/Associatividade ---
"""


# --- Transformer (Ajustado para tokens normais) ---
class AtomTransformer(Transformer):

    # --- Métodos Auxiliares ---
    # =====> CORRIGIDO: _unwrap_expression_tree <=====
    # Método para o novo wrapper (pode ser simples ou inexistente se @v_args funcionar)
    @v_args(inline=True) # Tenta passar o filho diretamente (None ou Tree)
    def decl_param_list_wrapper(self, child=None):
        """ Retorna a Tree 'decl_param_list_varargs' ou None. """
        # Se for None (sem params), retorna None.
        # Se for a Tree 'decl_param_list_varargs', retorna a Tree.
        # Se for a Tree 'handle_varargs_only', retorna ela (será tratada em mk_func_decl)
        return child
        
    def process_decl_params(self, items: List) -> Tuple[List[ast.Type], bool]:
        """
        Processa os itens da regra param_list_for_decl (alternativa com tipos).
        Sempre retorna (List[Type], is_vararg).
        """
        param_types: List[ast.Type] = []
        is_vararg = False
        for item in items:
            target_item = item
            if isinstance(item, Tree):
                 transform_method = getattr(self, item.data, None)
                 if transform_method:
                     try: target_item = transform_method(item.children)
                     except Exception: target_item = None
                 else: target_item = None

            if isinstance(target_item, ast.Type):
                param_types.append(target_item)
            elif isinstance(target_item, Token) and target_item.type == 'VARARGS':
                is_vararg = True
            # Ignora COMMA e outros
        return param_types, is_vararg
        
    def type_list(self, items: List) -> List[ast.Type]:
        """ Coleta nós de tipo de uma lista, ignorando vírgulas. """
        types = []
        # print(f"DEBUG Parser: type_list - items recebidos: {items!r}") # DEBUG
        for item in items:
            target_item = item
            # Se for uma Tree, tenta transformar (Lark pode não fazer isso automaticamente aqui)
            if isinstance(item, Tree):
                 transform_method = getattr(self, item.data, None)
                 if transform_method:
                      try:
                           target_item = transform_method(item.children)
                           # print(f"  DEBUG type_list: Tree '{item.data}' transformada em {type(target_item).__name__}") # DEBUG
                      except Exception as e:
                           print(f"  WARN type_list: Falha ao transformar Tree '{item.data}': {e}")
                           target_item = None
                 else:
                      print(f"  WARN type_list: Tree '{item.data}' sem transformer, ignorando.")
                      target_item = None

            # Adiciona se for um nó Type válido
            if isinstance(target_item, ast.Type):
                types.append(target_item)
            elif isinstance(item, Token) and item.type == 'COMMA':
                 pass # Ignora vírgula
            elif target_item is not None:
                 print(f"  WARN type_list: Ignorando item inesperado: {type(target_item).__name__} ({target_item!r})")
        # print(f"DEBUG Parser: type_list - retornando {len(types)} tipos.") # DEBUG
        return types
        
    # Novo método para criar o nó ast.FunctionType
    def mk_function_type(self, items: List) -> ast.FunctionType:
        # Estrutura esperada: [KW_FUNC, LPAREN, (zero ou mais nós Type/COMMA), RPAREN, ARROW, ReturnType]
        # print(f"DEBUG Parser: mk_function_type - items recebidos: {items!r}") # DEBUG
        param_types = []
        return_type_node: Optional[ast.Type] = None
        idx = 0

        # Pula KW_FUNC e LPAREN
        if not (isinstance(items[idx], Token) and items[idx].type == 'KW_FUNC'):
            raise ValueError("mk_function_type: Falta KW_FUNC")
        idx += 1
        if not (isinstance(items[idx], Token) and items[idx].type == 'LPAREN'):
            raise ValueError("mk_function_type: Falta LPAREN")
        idx += 1

        # Coleta tipos de parâmetros até encontrar RPAREN
        while idx < len(items):
            item = items[idx]
            if isinstance(item, Token) and item.type == 'RPAREN':
                idx += 1 # Consome RPAREN
                break # Fim dos parâmetros
            elif isinstance(item, ast.Type):
                param_types.append(item)
                idx += 1
            elif isinstance(item, Token) and item.type == 'COMMA':
                idx += 1 # Ignora vírgula
            elif isinstance(item, Tree) and item.data == 'type':
                 type_node = self._transform_tree(item)
                 if isinstance(type_node, ast.Type):
                     param_types.append(type_node)
                 else:
                     raise TypeError(f"mk_function_type: Falha ao transformar sub-árvore 'type'")
                 idx += 1
            else:
                raise ValueError(f"mk_function_type: Item inesperado '{item!r}' na lista de parâmetros.")
        # Verifica se o loop parou porque encontrou RPAREN (idx foi incrementado)
        # ou se chegou ao fim dos itens sem encontrar RPAREN (erro)
        if idx > len(items): # Se break não ocorreu e idx ultrapassou
             raise ValueError("mk_function_type: RPAREN não encontrado após lista de parâmetros.")

        # Verifica ARROW
        # ===> Correção Final na Condição e f-string <===
        if idx >= len(items) or not (isinstance(items[idx], Token) and items[idx].type == 'ARROW'):
            # Calcula a representação do item problemático FORA da f-string
            if idx >= len(items):
                got_repr = "'Fim dos Itens'" # String literal para clareza
            else:
                # Usa repr() padrão que é mais seguro que !r dentro de lógica complexa
                got_repr = repr(items[idx])
            # Agora usa a variável na f-string
            raise ValueError(f"mk_function_type: Esperava ARROW após parênteses, got {got_repr}")
        # ==============================================
        idx += 1 # Incrementa o índice após verificar o ARROW

        # Obtém e valida tipo de retorno
        if idx >= len(items):
            raise ValueError("mk_function_type: Tipo de retorno faltando após ARROW")
        return_type_intermediate = items[idx]
        if isinstance(return_type_intermediate, ast.Type):
            return_type_node = return_type_intermediate
        elif isinstance(return_type_intermediate, Tree):
             transform_method_name = getattr(return_type_intermediate, 'data', '')
             transform_method = getattr(self, transform_method_name, None)
             if transform_method:
                  resolved_type = transform_method(return_type_intermediate.children)
                  if isinstance(resolved_type, ast.Type):
                      return_type_node = resolved_type
                  else:
                      raise TypeError(f"Transformer '{transform_method_name}' não retornou Type")
             else:
                  raise TypeError(f"Tipo retorno Tree sem transformer: {transform_method_name}")
        else:
             raise TypeError(f"Tipo de retorno inesperado: {type(return_type_intermediate)}")

        # is_var_arg (sempre False com gramática atual para func type)
        is_vararg = False

        # Cria o nó final
        # print(f"  DEBUG mk_function_type: Params={param_types}, Return={return_type_node}, VarArg={is_vararg}")
        return ast.FunctionType(param_types=param_types, return_type=return_type_node, is_var_arg=is_vararg)
   
    # NOVO MÉTODO para tratar o caso de apenas VARARGS
    def handle_varargs_only(self, items: List) -> Tuple[List[ast.Type], bool]:
         """ Processa o caso onde só há '...' nos parâmetros. """
         return [], True # Retorna lista vazia de tipos e is_vararg=True   
        
    # NOVO MÉTODO para a alternativa vazia
    def empty_param_list(self, items):
         """ Processa o caso onde não há parâmetros nem VARARGS. """
         return None # Retorna None para indicar ausência de parâmetros
         
    # =====> CORRIGIDO: _unwrap_expression_tree <=====    
    def _unwrap_expression_tree(self, node: Union[Tree, ast.Node, Token]) -> ast.Expression:
        """Desembrulha árvores de regras intermediárias e tenta transformar Trees finais."""
        if isinstance(node, ast.Expression): return node
        if isinstance(node, Token):
             if node.type == 'CNAME': return ast.Identifier(str(node))
             elif node.type in ('INTEGER_LITERAL', 'STRING_LITERAL', 'BYTE_STRING_LITERAL', 'CHAR_LITERAL', 'TRUE', 'FALSE'):
                  if node.type == 'INTEGER_LITERAL': return ast.IntegerLiteral(int(str(node)))
                  if node.type == 'STRING_LITERAL': return ast.StringLiteral(node.value[1:-1])
                  if node.type == 'BYTE_STRING_LITERAL': return ast.ByteStringLiteral(eval(str(node)))
                  if node.type == 'CHAR_LITERAL': v=eval(str(node)); assert len(v)==1; return ast.CharLiteral(v)
                  if node.type == 'TRUE': return ast.BooleanLiteral(True)
                  if node.type == 'FALSE': return ast.BooleanLiteral(False)
             raise TypeError(f"_unwrap: Cannot convert Token type {node.type} to Expr: {node!r}")
        if not isinstance(node, Tree): raise TypeError(f"_unwrap: Input type {type(node)} not Tree/Expr/Token")

        intermediate_rules = {
            "expression", "logical_or_expr", "logical_and_expr", "equality_expr",
            "comparison_expr", "additive_expr", "multiplicative_expr", "cast_expr",
            "unary_expr", "postfix_expr", "primary_expr", "lvalue", "statement",
            "grouped_expression"
        }
        current_node = node
        visited_datas = set()

        while isinstance(current_node, Tree):
            tree_data = getattr(current_node, 'data', None);
            if tree_data is None: break
            # Evita recursão infinita se uma regra estiver mal definida
            # Usar id da árvore para detectar ciclo exato
            node_id = id(current_node)
            if node_id in visited_datas: raise RecursionError(f"Loop detected in _unwrap for rule '{tree_data}'")
            visited_datas.add(node_id)

            if tree_data == "grouped_expression":
                 if len(current_node.children) == 3: current_node = current_node.children[1]; continue
                 else: raise ValueError(f"_unwrap grouped_expression invalid structure: {current_node!r}")

            can_unwrap = False
            if tree_data in intermediate_rules and len(current_node.children) == 1:
                 # Ajustar lógica de can_unwrap se necessário (como antes)
                 if tree_data == 'cast_expr':
                     child = current_node.children[0]
                     if isinstance(child, (Tree, ast.Expression)): can_unwrap = True
                 elif tree_data == 'unary_expr':
                     op_token_types = {'BANG', 'MINUS', 'STAR', 'AMPERSAND'}
                     is_prefix_op = isinstance(current_node.children[0], Token) and current_node.children[0].type in op_token_types
                     is_refmut = len(current_node.children) >=2 and isinstance(current_node.children[0], Token) and current_node.children[0].type == 'AMPERSAND' and isinstance(current_node.children[1], Token) and current_node.children[1].type == 'MUT'
                     if not (is_prefix_op or is_refmut): can_unwrap = True
                 else: can_unwrap = True

            if can_unwrap: current_node = current_node.children[0]
            else: break

        # Verificação Final
        if isinstance(current_node, ast.Expression): return current_node
        elif isinstance(current_node, Token) and current_node.type == 'CNAME': return ast.Identifier(str(current_node))
        # =====> MODIFICADO: Tenta transformar a Tree final <=====
        elif isinstance(current_node, Tree):
             # Se ainda é uma Tree, tenta chamar o método transformer associado a ela
             rule_name = getattr(current_node, 'data', None)
             transform_method = getattr(self, rule_name, None)
             # print(f"DEBUG: _unwrap trying to transform final Tree: {rule_name}") # Debug opcional
             if transform_method:
                 try:
                     # Chama o método transformer (ex: bin_op_expr, mk_cast_expr, etc.)
                     transformed_node = transform_method(current_node.children)
                     # Verifica se o resultado é uma Expression
                     if isinstance(transformed_node, ast.Expression):
                         return transformed_node
                     else:
                         # Se o transformer não retornou uma Expression, algo está errado
                         raise TypeError(f"_unwrap: Transformer method '{rule_name}' did not return an Expression node, got {type(transformed_node)}")
                 except Exception as e:
                     # Erro durante a transformação da regra específica
                     raise TypeError(f"_unwrap failed calling transformer for '{rule_name}': {e}") from e
             else:
                 # Não há método transformer para esta regra de árvore? Erro.
                 raise TypeError(f"_unwrap final type error: No transformer method for Tree rule '{rule_name}'")
        else:
             # Não é Expression, CNAME Token ou Tree -> Erro
             raise TypeError(f"_unwrap final type error: Expected Expression, got {type(current_node)}")
    # ==========================================================================

    # ... (Restante do Transformer) ...
    def _build_binary_op_tree(self, items: List) -> ast.Expression:
        left = self._unwrap_expression_tree(items[0])
        idx = 1
        while idx < len(items):
            op_token = items[idx]; right_intermediate = items[idx+1]; right = self._unwrap_expression_tree(right_intermediate)
            op_str = str(op_token.value) if isinstance(op_token, Token) else str(op_token)
            if not op_str: raise ValueError(f"_build_binary_op_tree: Operator token '{op_token!r}' resulted in empty operator string.")
            left = ast.BinaryOp(op=op_str, left=left, right=right); idx += 2
        return left
    def _collect_statements(self, items: List) -> List[ast.Statement]:
        collected = []
        for item in items:
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                if rule_name == 'statement' and len(item.children) == 1:
                    child = item.children[0]
                    if isinstance(child, ast.Statement): target_item = child
                    elif isinstance(child, Tree):
                        try:
                            transform_method = getattr(self, child.data, None)
                            if transform_method: target_item = transform_method(child.children)
                            else: target_item = None
                        except Exception as e: raise TypeError(f"_collect failed transforming {child.data}: {e}")
                    else: target_item = None
                else: # Try transforming directly if rule name matches a statement type
                    transform_method = getattr(self, rule_name, None)
                    if transform_method:
                        try: target_item = transform_method(item.children)
                        except Exception as e: raise TypeError(f"_collect failed transforming {rule_name}: {e}")
                    else: target_item = None # Ignore other trees
            if isinstance(target_item, ast.Statement): collected.append(target_item)
            elif target_item is None or isinstance(target_item, Token): continue
            else: raise TypeError(f"_collect_statements: Unexpected item type {type(target_item)}: {target_item!r}")
        return collected
    def _collect_until_end(self, items: List, expected_type: type) -> List[ast.Node]:
        collected = []
        for item in items:
            if isinstance(item, Token) and item.type == 'KW_END': break
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                transform_method = getattr(self, rule_name, None)
                if transform_method:
                    try: target_item = transform_method(item.children)
                    except Exception as e: raise TypeError(f"_collect failed transforming {rule_name}: {e}")
                else: target_item = None
            if isinstance(target_item, expected_type): collected.append(target_item)
            elif target_item is None or isinstance(target_item, Token): continue
            else: raise TypeError(f"_collect_until_end({expected_type.__name__}): Unexpected item type {type(target_item)}: {target_item!r}")
        return collected
    # ==========================================================================

    # ... (Restante do Transformer) ...
    def _build_binary_op_tree(self, items: List) -> ast.Expression:
        left = self._unwrap_expression_tree(items[0])
        idx = 1
        while idx < len(items):
            op_token = items[idx]; right_intermediate = items[idx+1]; right = self._unwrap_expression_tree(right_intermediate)
            op_str = str(op_token.value) if isinstance(op_token, Token) else str(op_token)
            if not op_str: raise ValueError(f"_build_binary_op_tree: Operator token '{op_token!r}' resulted in empty operator string.")
            left = ast.BinaryOp(op=op_str, left=left, right=right); idx += 2
        return left
    def _collect_statements(self, items: List) -> List[ast.Statement]:
        collected = []
        for item in items:
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                if rule_name == 'statement' and len(item.children) == 1:
                    child = item.children[0]
                    if isinstance(child, ast.Statement): target_item = child
                    elif isinstance(child, Tree):
                        try:
                            transform_method = getattr(self, child.data, None)
                            if transform_method: target_item = transform_method(child.children)
                            else: target_item = None
                        except Exception as e: raise TypeError(f"_collect failed transforming {child.data}: {e}")
                    else: target_item = None
                else: target_item = None
            if isinstance(target_item, ast.Statement): collected.append(target_item)
            elif target_item is None or isinstance(target_item, Token): continue
            else: raise TypeError(f"_collect_statements: Unexpected item type {type(target_item)}: {target_item!r}")
        return collected
    def _collect_until_end(self, items: List, expected_type: type) -> List[ast.Node]:
        collected = []
        for item in items:
            if isinstance(item, Token) and item.type == 'KW_END': break
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                transform_method = getattr(self, rule_name, None)
                if transform_method:
                     try: target_item = transform_method(item.children)
                     except Exception as e: raise TypeError(f"_collect failed transforming {rule_name}: {e}")
                else: target_item = None
            if isinstance(target_item, expected_type): collected.append(target_item)
            elif target_item is None or isinstance(target_item, Token): continue
            else: raise TypeError(f"_collect_until_end({expected_type.__name__}): Unexpected item type {type(target_item)}: {target_item!r}")
        return collected

    def _build_binary_op_tree(self, items: List) -> ast.Expression:
        # Assumes items are already unwrapped AST nodes by the bin_op_expr handler
        left = items[0]
        idx = 1
        while idx < len(items):
            op_token = items[idx]; right = items[idx+1]
            op_str = str(op_token.value)
            left = ast.BinaryOp(op=op_str, left=left, right=right); idx += 2
        return left

    def _collect_statements(self, items: List) -> List[ast.Statement]:
        collected = []
        for item in items:
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                # Try to transform based on rule name if it wasn't transformed automatically
                transform_method = getattr(self, rule_name, None)
                if transform_method:
                     try: target_item = transform_method(item.children)
                     except Exception as e: raise TypeError(f"_collect failed transforming {rule_name}: {e}")
                else: target_item = None # Ignore trees we can't transform
            # Append only if the final result is a Statement
            if isinstance(target_item, ast.Statement): collected.append(target_item)
            elif target_item is None or isinstance(target_item, Token): continue
            # else: raise TypeError(f"_collect_statements: Unexpected item type {type(target_item)}: {target_item!r}") # Be less strict maybe?
        return collected

    def _collect_until_end(self, items: List, expected_type: type) -> List[ast.Node]:
        collected = []
        for item in items:
            if isinstance(item, Token) and item.type == 'KW_END': break
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                transform_method = getattr(self, rule_name, None)
                if transform_method:
                     try: target_item = transform_method(item.children)
                     except Exception as e: raise TypeError(f"_collect failed transforming {rule_name}: {e}")
                else: target_item = None
            if isinstance(target_item, expected_type): collected.append(target_item)
            elif target_item is None or isinstance(target_item, Token): continue
            else: raise TypeError(f"_collect_until_end({expected_type.__name__}): Unexpected item type {type(target_item)}: {target_item!r}")
        return collected
    def _collect_struct_fields(self, items: List) -> List[ast.StructFieldDef]: return self._collect_until_end(items, ast.StructFieldDef)
    def _collect_enum_variants(self, items: List) -> List[ast.EnumVariantDef]: return self._collect_until_end(items, ast.EnumVariantDef)
    def _collect_func_decls(self, items: List) -> List[ast.FunctionDecl]: return self._collect_until_end(items, ast.FunctionDecl)
    def CNAME(self, token: Token) -> Token: return token
    @v_args(inline=True)
    def mk_identifier(self, name_token: Token) -> ast.Identifier: return ast.Identifier(str(name_token))
    @v_args(inline=True)
    def abi_string(self, token: Token) -> ast.StringLiteral: return ast.StringLiteral(token.value[1:-1])
    def MUT_OR_CONST(self, token: Token) -> str: return str(token)
    def MUT(self, token: Token) -> Token: return token
    @v_args(inline=True)
    def mk_integer_literal(self, t: Token) -> ast.IntegerLiteral:
        text = str(t)
        cleaned_text = text.replace('_', '')
        value: int
        if cleaned_text.startswith(('0x', '0X')):
            value = int(cleaned_text, 16)
        elif cleaned_text.startswith(('0o', '0O')):
             value = int(cleaned_text[2:], 8) if len(cleaned_text) > 2 else 0
        elif cleaned_text.startswith(('0b', '0B')):
             value = int(cleaned_text[2:], 2) if len(cleaned_text) > 2 else 0
        else:
             value = int(cleaned_text, 10)
        return ast.IntegerLiteral(value=value)

    # PRECISAMOS mapear os novos terminais para INTEGER_LITERAL se não o fizermos na gramática
    # Se a regra INTEGER_LITERAL: HEX_INTEGER | ... já faz isso, ok.
    # Senão, precisaríamos de:
    # def HEX_INTEGER(self, t): return self.mk_integer_literal(t)
    # def OCT_INTEGER(self, t): return self.mk_integer_literal(t)
    # def BIN_INTEGER(self, t): return self.mk_integer_literal(t)
    # def DEC_INTEGER(self, t): return self.mk_integer_literal(t)
    # Mas a regra na gramática já deve cuidar disso.
    @v_args(inline=True)
    def mk_string_literal(self, t: Token) -> ast.StringLiteral:
        # t.value inclui as aspas delimitadoras, ex: "\"Hello\\nWorld\""
        raw_string_content = t.value[1:-1] # Remove aspas: "Hello\\nWorld"
        
        # Interpreta as sequências de escape C-like
        # Ex: "\\n" -> "\n", "\\t" -> "\t", "\\\\" -> "\\"
        import codecs
        try:
            # codecs.escape_decode retorna uma tupla (decoded_bytes, length_consumed)
            processed_string = codecs.escape_decode(bytes(raw_string_content, 'utf-8'))[0].decode('utf-8')
        except Exception as e:
            print(f"WARN: Falha ao processar escapes na string literal: '{raw_string_content}'. Erro: {e}. Usando string como está.")
            processed_string = raw_string_content # Fallback
            
        return ast.StringLiteral(processed_string)
    @v_args(inline=True)
    def mk_bytestring_literal(self, t: Token) -> ast.ByteStringLiteral: return ast.ByteStringLiteral(eval(str(t)))
    @v_args(inline=True)
    def mk_char_literal(self, t: Token) -> ast.CharLiteral:
        # t.value inclui as aspas, ex: "'\\n'"
        raw_char_content = t.value[1:-1] # Remove aspas: "\\n"
        import codecs
        try:
            processed_char = codecs.escape_decode(bytes(raw_char_content, 'utf-8'))[0].decode('utf-8')
            if len(processed_char) != 1:
                # Isso pode acontecer para escapes inválidos ou múltiplos caracteres que não foram pegos pelo lexer
                print(f"WARN: Char literal '{raw_char_content}' resultou em string de comprimento != 1 após processar escapes: '{processed_char}'. Usando o primeiro caractere.")
                if not processed_char: # Se string vazia após decode
                    raise ValueError("Char literal resultou em string vazia.")
                processed_char = processed_char[0]
        except Exception as e:
            print(f"WARN: Falha ao processar escapes no char literal: '{raw_char_content}'. Erro: {e}. Usando como está (pode falhar).")
            processed_char = raw_char_content # Fallback
            if len(processed_char) != 1:
                raise ValueError(f"Char literal inválido: '{raw_char_content}'")
        return ast.CharLiteral(processed_char)
    def mk_bool_literal_true(self, _) -> ast.BooleanLiteral: return ast.BooleanLiteral(True)
    def mk_bool_literal_false(self, _) -> ast.BooleanLiteral: return ast.BooleanLiteral(False)
    @v_args(inline=True)
    def mk_custom_or_primitive_type(self, id_node_or_tok: Union[ast.Identifier, Token]) -> ast.Type:
        id_node = id_node_or_tok
        if isinstance(id_node_or_tok, Token): id_node = self.mk_identifier(id_node_or_tok)
        if not isinstance(id_node, ast.Identifier): raise TypeError("mk_custom_or_primitive_type: input not Identifier")
        primitives = {"int","uint","bool","char","i8","u8","i16","u16","i32","u32","i64","u64","usize","isize"}
        name = id_node.name
        return ast.PrimitiveType(name) if name in primitives else ast.CustomType(id_node)
    def mk_unit_type(self, _) -> ast.UnitType: return ast.UnitType()
    def mk_pointer_type(self, items) -> ast.PointerType: # Uses STAR normal
        pointee_type = items[2]
        if not isinstance(pointee_type, ast.Type): raise TypeError(f"mk_pointer_type: pointee não é Type")
        mod_tok_val = items[1]
        is_mutable = (mod_tok_val == "mut")
        return ast.PointerType(pointee_type=pointee_type, is_mutable=is_mutable)
    def mk_reference_type(self, items) -> ast.ReferenceType: # Uses AMPERSAND normal
        is_mutable = False; type_node = None
        if len(items) == 2: type_node = items[1]
        elif len(items) == 3:
             if isinstance(items[1], Token) and items[1].type == "MUT": is_mutable = True; type_node = items[2]
             else: raise ValueError(f"mk_reference_type (3 itens): esperava MUT token")
        else: raise ValueError(f"mk_reference_type: Esperava 2 ou 3 itens")
        if not isinstance(type_node, ast.Type): raise TypeError(f"mk_reference_type: type_node não é Type")
        return ast.ReferenceType(referenced_type=type_node, is_mutable=is_mutable)
    def mk_slice_type(self, items) -> ast.SliceType: # Uses AMPERSAND normal
        is_mutable = False; type_node_index = -1
        if len(items) == 4: type_node_index = 3 # &, [, Type, ]
        elif len(items) == 5: # &, MUT, [, Type, ]
             if isinstance(items[1], Token) and items[1].type == "MUT": is_mutable = True; type_node_index = 4
             else: raise ValueError(f"mk_slice_type (5 itens): esperava MUT token")
        else: raise ValueError(f"mk_slice_type: Esperava 4 ou 5 itens")
        type_node = items[type_node_index - 1]
        if not isinstance(type_node, ast.Type): raise TypeError(f"mk_slice_type: type_node não é Type")
        return ast.SliceType(element_type=type_node, is_mutable=is_mutable)
    def mk_array_type(self, items) -> ast.ArrayType:
        type_node, size_intermediate = items[1], items[3]
        size_node = self._unwrap_expression_tree(size_intermediate)
        if not isinstance(type_node, ast.Type): raise TypeError(f"mk_array_type: elem type não é Type")
        if not isinstance(size_node, ast.Expression): raise TypeError(f"mk_array_type: size não é Expr")
        return ast.ArrayType(element_type=type_node, size=size_node)
    @v_args(inline=True)
    def mk_parameter(self, n: Union[ast.Identifier, Token], t: ast.Type) -> ast.Parameter:
        name_node = n
        if isinstance(n, Token): name_node = self.mk_identifier(n)
        if not isinstance(name_node, ast.Identifier): raise TypeError("mk_parameter: n not Identifier")
        if not isinstance(t, ast.Type): raise TypeError("mk_parameter: t not Type")
        return ast.Parameter(name=name_node, type=t)
    def def_param_list(self, params_and_commas: List) -> List[ast.Parameter]:
        params = [p for p in params_and_commas if isinstance(p, ast.Parameter)]
        return params
    def decl_param_list(self, types_and_commas: List) -> List[ast.Type]:
        types = [t for t in types_and_commas if isinstance(t, ast.Type)]
        return types
    def arg_list(self, items: List) -> List[ast.Expression]:
        # Processa a lista de argumentos e vírgulas
        args = []
        for item in items:
            # --- CORREÇÃO AQUI ---
            # Pula os tokens de vírgula diretamente
            if isinstance(item, Token) and item.type == 'COMMA':
                continue
            # --- FIM CORREÇÃO ---

            # Tenta desembrulhar os outros itens (devem ser expressões ou árvores)
            try:
                unwrapped = self._unwrap_expression_tree(item)
                if isinstance(unwrapped, ast.Expression):
                    args.append(unwrapped)
                elif unwrapped is not None:
                     print(f"WARN: arg_list ignorou item inesperado (após unwrap): {type(unwrapped)}")
            except TypeError as e:
                 print(f"WARN: arg_list encontrou erro ao desembrulhar: {e}. Item original: {item!r}")
            except Exception as e_unwrap:
                 print(f"WARN: arg_list encontrou erro inesperado ao desembrulhar: {e_unwrap}. Item original: {item!r}")

        return args
    def VARARGS(self, token: Token) -> Token: return token
    def mk_program(self, items: List) -> ast.Program:
        # print(f"DEBUG Transformer: Entrando mk_program com {len(items)} itens:") # DEBUG
        valid_items = []
        ignored_items = []
        for i, item in enumerate(items):
            # Tenta transformar Trees que não foram transformadas automaticamente
            target_item = item
            if isinstance(item, Tree):
                rule_name = item.data
                transform_method = getattr(self, rule_name, None)
                if transform_method:
                    try: target_item = transform_method(item.children)
                    except Exception as e: print(f"  WARN mk_program: Falha ao transformar {rule_name}: {e}"); target_item=None
                else: target_item = None # Ignora Tree sem transformer

            # Verifica se o item final é um nó AST esperado no top-level
            if isinstance(target_item, (ast.FunctionDef, ast.StructDef, ast.EnumDef, ast.ConstDef, ast.ExternBlock, ast.ImportDecl)):
                 valid_items.append(target_item)
                 # print(f"  DEBUG mk_program: Item {i} (Tipo: {type(target_item).__name__}) adicionado.") # DEBUG
            elif target_item is not None:
                 ignored_items.append(target_item)
                 print(f"  WARN mk_program: Item {i} (Tipo: {type(target_item).__name__}) IGNORADO.") # DEBUG
            # Ignora None silenciosamente

        if ignored_items:
             print(f"WARN: mk_program ignorou {len(ignored_items)} itens não reconhecidos no top-level.")
        # print(f"DEBUG Transformer: Saindo mk_program com {len(valid_items)} itens válidos.") # DEBUG
        return ast.Program(body=valid_items)
    @v_args(inline=True)
    def mk_import_decl(self, path_node: ast.StringLiteral) -> ast.ImportDecl:
        if not isinstance(path_node, ast.StringLiteral): raise TypeError("mk_import_decl: path not StringLiteral")
        return ast.ImportDecl(path=path_node)
    def mk_const_def(self, items: List) -> ast.ConstDef:
        # print(f"DEBUG Transformer: Executando mk_const_def...")
        name, type_annot, value_intermediate = items[1], items[2], items[3]
        if isinstance(name, Token): name = self.mk_identifier(name)
        if not isinstance(name, ast.Identifier): raise TypeError("mk_const_def: name not Identifier")
        if not isinstance(type_annot, ast.Type): raise TypeError("mk_const_def: type_annot not Type")
        value_node = self._unwrap_expression_tree(value_intermediate)
        return ast.ConstDef(name=name, type_annot=type_annot, value=value_node)
    def mk_struct_def(self, items: List) -> ast.StructDef:
        # print(f"DEBUG Transformer: Executando mk_struct_def...")
        name_node = items[1]
        if isinstance(name_node, Token): name_node = self.mk_identifier(name_node)
        if not isinstance(name_node, ast.Identifier): raise TypeError("mk_struct_def: name not Identifier")
        fields = self._collect_struct_fields(items[2:])
        return ast.StructDef(name=name_node, fields=fields)
    def mk_struct_field_def(self, items: List) -> ast.StructFieldDef:
        name_node, type_node = items[0], items[1]
        if isinstance(name_node, Token): name_node = self.mk_identifier(name_node)
        if not isinstance(name_node, ast.Identifier): raise TypeError("mk_struct_field_def: name not Identifier")
        if not isinstance(type_node, ast.Type): raise TypeError("mk_struct_field_def: type not Type")
        return ast.StructFieldDef(name=name_node, type=type_node)
    def mk_enum_def(self, items: List) -> ast.EnumDef:
        # print(f"DEBUG Transformer: Executando mk_enum_def...")
        name_node = items[1]
        if isinstance(name_node, Token): name_node = self.mk_identifier(name_node)
        if not isinstance(name_node, ast.Identifier): raise TypeError("mk_enum_def: name not Identifier")
        variants = self._collect_enum_variants(items[2:])
        return ast.EnumDef(name=name_node, variants=variants)
    def mk_enum_variant_def(self, items: List) -> ast.EnumVariantDef:
        name_node = items[0]
        if isinstance(name_node, Token): name_node = self.mk_identifier(name_node)
        if not isinstance(name_node, ast.Identifier): raise TypeError("mk_enum_variant_def: name not Identifier")
        return ast.EnumVariantDef(name=name_node)
    def mk_extern_block(self, items) -> ast.ExternBlock:
        # print(f"DEBUG Transformer: Executando mk_extern_block...")
        abi_node = items[1]
        if not isinstance(abi_node, ast.StringLiteral): raise TypeError("mk_extern_block: ABI not StringLiteral")
        decls = self._collect_func_decls(items[2:])
        return ast.ExternBlock(abi=abi_node, declarations=decls)
        
    # AJUSTE em mk_func_decl para usar o wrapper
    # AJUSTE em mk_func_decl para usar o resultado de process_decl_params/handle_varargs_only
    # AJUSTE em mk_func_decl (confirmar que está como abaixo)
    
    def mk_func_def(self, items: List) -> ast.FunctionDef:
        # items: [KW_FUNC, Name(Id/Tok), LPAREN, ParamList(List[Param]) | Param(Node) | RPAREN, RPAREN, ARROW, ReturnType(Type), Stmt*, KW_END]
        # print(f"DEBUG Parser: Entrando mk_func_def com {len(items)} itens: {items!r}") # DEBUG com itens
        name_node: Optional[ast.Identifier] = None
        params: List[ast.Parameter] = []
        return_type_node: Optional[ast.Type] = None
        body_stmts: List[ast.Statement] = []
        item_iter = iter(items) # Usar iterador

        try:
            # 1. KW_FUNC
            token = next(item_iter); assert isinstance(token, Token) and token.type == 'KW_FUNC'
            # 2. Name
            name_intermediate = next(item_iter)
            if isinstance(name_intermediate, ast.Identifier): name_node = name_intermediate
            elif isinstance(name_intermediate, Token) and name_intermediate.type == 'CNAME': name_node = self.mk_identifier(name_intermediate)
            elif isinstance(name_intermediate, Tree) and name_intermediate.data == 'mk_identifier': name_node = self.mk_identifier(name_intermediate.children[0]) # Caso comum
            else: raise TypeError(f"Esperava Identifier ou CNAME para nome, got {type(name_intermediate)}")
            # print(f"  DEBUG Parser: Nome = {name_node.name}")

            # 3. LPAREN
            token = next(item_iter); assert isinstance(token, Token) and token.type == 'LPAREN'

            # 4. Params (pode ser lista, nó único Parameter, ou RPAREN diretamente se vazio)
            params_intermediate = next(item_iter)
            # --- CORREÇÃO AQUI ---
            if isinstance(params_intermediate, list): # Caso 1: Múltiplos parâmetros (def_param_list retornou lista)
                if all(isinstance(p, ast.Parameter) for p in params_intermediate): params = params_intermediate
                else: raise TypeError(f"Lista de parâmetros inválida: {params_intermediate}")
                token = next(item_iter); assert isinstance(token, Token) and token.type == 'RPAREN' # Consome RPAREN
            elif isinstance(params_intermediate, ast.Parameter): # Caso 2: Apenas um parâmetro
                params = [params_intermediate] # Cria a lista com o único parâmetro
                token = next(item_iter); assert isinstance(token, Token) and token.type == 'RPAREN' # Consome RPAREN
            # --- FIM CORREÇÃO ---
            elif isinstance(params_intermediate, Token) and params_intermediate.type == 'RPAREN': # Caso 3: Sem parâmetros
                params = [] # Já consumimos o RPAREN
            else: raise TypeError(f"Esperava lista de Params, um nó Parameter ou RPAREN, got {type(params_intermediate)}")
            # print(f"  DEBUG Parser: Params = {params}")

            # 5. ARROW
            token = next(item_iter); assert isinstance(token, Token) and token.type == 'ARROW'

            # 6. Return Type
            return_type_intermediate = next(item_iter)
            # --- USA _resolve_type do transformer para nós de tipo ---
            # Precisamos de uma função helper no transformer ou usar _unwrap?
            # Vamos tentar usar _transform_tree se existir, ou manualmente
            if isinstance(return_type_intermediate, ast.Type):
                 return_type_node = return_type_intermediate
            elif isinstance(return_type_intermediate, Tree):
                 # Tenta transformar a árvore do tipo
                 transform_method_name = getattr(return_type_intermediate, 'data', None)
                 transform_method = getattr(self, transform_method_name, None)
                 if transform_method:
                      resolved_type = transform_method(return_type_intermediate.children)
                      if isinstance(resolved_type, ast.Type):
                           return_type_node = resolved_type
                      else: raise TypeError(f"Transformer '{transform_method_name}' não retornou Type")
                 else: raise TypeError(f"Tipo de retorno Tree '{transform_method_name}' sem transformer")
            else: raise TypeError(f"Tipo de retorno inesperado: {type(return_type_intermediate)}")
            # -----------------------------------------------------------
            # print(f"  DEBUG Parser: Return Type = {return_type_node}") # Assume type_to_string existe

            # 7. Body Statements (coleta tudo até KW_END)
            body_items_intermediate = []
            for remaining_item in item_iter: # Itera sobre o restante
                 if isinstance(remaining_item, Token) and remaining_item.type == 'KW_END':
                      break # Fim
                 body_items_intermediate.append(remaining_item)
            body_stmts = self._collect_statements(body_items_intermediate) # Processa os itens coletados
            # print(f"  DEBUG Parser: Body Stmts = ({len(body_stmts)} statements)")

            # Cria o nó
            func_def_node = ast.FunctionDef(name=name_node, params=params, return_type=return_type_node, body=body_stmts)
            # print(f"DEBUG Parser: Saindo mk_func_def, retornando nó: {type(func_def_node)}")
            return func_def_node

        except (StopIteration, AssertionError, TypeError, ValueError) as e:
             print(f"ERROR: Falha interna em mk_func_def: {e}")
             # Tenta obter índice do iterador se ele tiver (não garantido)
             items_processed_count = 0
             # if hasattr(item_iter, '__length_hint__'): # Isso não funciona bem com next()
             #    items_processed_count = len(items) - item_iter.__length_hint__()
             # Vamos apenas mostrar os itens originais
             print(f"       Itens originais: {items!r}")
             import traceback
             traceback.print_exc()
             return None
    
    def mk_func_decl(self, items: List) -> ast.FunctionDecl:
        """
        Transforma os itens da regra func_decl em um nó AST FunctionDecl.
        Espera uma tupla (List[Type], bool) ou None da regra de parâmetros.
        """
        # Estrutura esperada de items:
        # [KW_FUNC, Name(Id/Tok), LPAREN, ParamResult(tuple/None), RPAREN, ARROW, ReturnType(Node/Tree), SEMICOLON]

        # Extrai nome
        name_node = items[1]
        # ... (transforma name_node se for Token) ...
        if not isinstance(name_node, ast.Identifier): raise TypeError(...)

        # Extrai e transforma tipo de retorno
        return_type_intermediate = items[-2]
        return_type_node = return_type_intermediate
        # ... (lógica de transformação do tipo de retorno como antes) ...
        if not isinstance(return_type_node, ast.Type): raise TypeError(...)


        # Processa a parte dos parâmetros
        param_result = items[3] # Resultado de process_decl_params, handle_varargs_only ou empty_param_list
        param_type_nodes: List[ast.Type] = []
        is_var_arg = False

        if isinstance(param_result, tuple) and len(param_result) == 2 and isinstance(param_result[0], list) and isinstance(param_result[1], bool):
            # Recebeu a tupla esperada de process_decl_params ou handle_varargs_only
            param_type_nodes, is_var_arg = param_result
        elif param_result is None:
            # Recebeu None de empty_param_list (Sem parâmetros e sem varargs)
             pass
        else:
            # Recebeu algo inesperado
            raise TypeError(f"mk_func_decl: Parte do parâmetro inesperada, esperava tupla (List[Type], bool) ou None, got {type(param_result)}")


        # --- DEBUG (Mantido) ---
        # print(f"DEBUG Parser: mk_func_decl for '{name_node.name}': is_var_arg = {is_var_arg} (Param Types: {[repr(p) for p in param_type_nodes]})")
        # --- FIM DEBUG ---

        # Cria nós Parameter com nomes dummy
        params: List[ast.Parameter] = [
            ast.Parameter(name=ast.Identifier(f"_extern_param{idx}"), type=pt)
            for idx, pt in enumerate(param_type_nodes)
        ]

        # Cria e retorna o nó FunctionDecl
        return ast.FunctionDecl(
            name=name_node,
            params=params,
            return_type=return_type_node,
            is_var_arg=is_var_arg
        )
    def statement(self, items):
        child = items[0]
        if isinstance(child, ast.Statement): return child
        elif isinstance(child, Tree):
             try: return getattr(self, child.data)(child.children)
             except Exception as e: raise TypeError(f"statement failed transforming {child.data}: {e}")
        raise TypeError(f"Statement rule expected Statement or Tree, got {type(child)}")
    def mk_let_binding(self, items: List) -> ast.LetBinding:
        name_node = items[1]; type_annot = None; value_intermediate = None
        if isinstance(name_node, Token): name_node = self.mk_identifier(name_node)
        pos = 2
        if pos < len(items) and isinstance(items[pos], ast.Type): type_annot = items[pos]; pos += 1
        value_index = pos
        if value_index < len(items): value_intermediate = items[value_index]
        else: raise ValueError(f"let: missing value")
        value_node = self._unwrap_expression_tree(value_intermediate)
        return ast.LetBinding(name=name_node, type_annot=type_annot, value=value_node)
    def mk_mut_binding(self, items: List) -> ast.MutBinding:
        name_node = items[1]; type_annot = None; value_intermediate = None
        if isinstance(name_node, Token): name_node = self.mk_identifier(name_node)
        pos = 2
        if pos < len(items) and isinstance(items[pos], ast.Type): type_annot = items[pos]; pos += 1
        value_index = pos
        if value_index < len(items): value_intermediate = items[value_index]
        else: raise ValueError(f"mut: missing value")
        value_node = self._unwrap_expression_tree(value_intermediate)
        return ast.MutBinding(name=name_node, type_annot=type_annot, value=value_node)
    def mk_assignment(self, items: List) -> ast.Assignment:
        # items: [lvalue_node, Token(EQ), expression_node]
        # Índices corretos são 0 e 2
        if len(items) != 3:
             # Isso pode acontecer se houver erro no parsing/transformação dos filhos
             raise ValueError(f"mk_assignment esperava 3 filhos, recebeu {len(items)}: {items!r}")

        target_intermediate = items[0]
        # O token EQ está em items[1], ignoramos ele
        value_intermediate = items[2]

        target_node = self._unwrap_expression_tree(target_intermediate)
        value_node = self._unwrap_expression_tree(value_intermediate)

        # Validação (opcional, mas boa prática)
        if not isinstance(target_node, ast.Expression): # lvalue deve ser uma expressão
            raise TypeError(f"mk_assignment: target (lvalue) não é Expression, got {type(target_node)}")
        if not isinstance(value_node, ast.Expression):
            raise TypeError(f"mk_assignment: value não é Expression, got {type(value_node)}")

        return ast.Assignment(target=target_node, value=value_node)
    def mk_return_stmt(self, items) -> ast.ReturnStmt:
        value_node: Optional[ast.Expression] = None
        if len(items) > 1: value_node = self._unwrap_expression_tree(items[1])
        return ast.ReturnStmt(value=value_node)
    def mk_break_stmt(self, items) -> ast.BreakStmt: return ast.BreakStmt()
    def mk_continue_stmt(self, items) -> ast.ContinueStmt: return ast.ContinueStmt()
    def mk_expr_statement(self, items: List) -> ast.Statement:
         expr_node = self._unwrap_expression_tree(items[0])
         return ast.ExpressionStatement(expression=expr_node)
    def mk_if_stmt(self, items: List) -> ast.IfStmt:
        cond_node = self._unwrap_expression_tree(items[1])
        if not isinstance(cond_node, ast.Expression): raise TypeError("mk_if_stmt: Condition node is not an Expression.")
        kw_end_token = items[-1]
        if not (isinstance(kw_end_token, Token) and kw_end_token.type == 'KW_END'): raise ValueError(f"mk_if_stmt: Expected KW_END at the end, got {kw_end_token!r}")
        potential_else_clause = items[-2]
        else_result_node: Optional[Union[ast.IfStmt, List[ast.Statement]]] = None
        then_end_index = -1
        if isinstance(potential_else_clause, (ast.IfStmt, list)) or (isinstance(potential_else_clause, Tree) and potential_else_clause.data == 'else_clause'):
             if isinstance(potential_else_clause, Tree): else_result_node = self.else_clause(potential_else_clause.children)
             else: else_result_node = potential_else_clause
             then_end_index = len(items) - 2
        else: else_result_node = None; then_end_index = len(items) - 1
        then_items_to_collect = items[2:then_end_index]
        then_block = self._collect_statements(then_items_to_collect)
        if else_result_node is not None:
             if not isinstance(else_result_node, (ast.IfStmt, list)): raise TypeError(f"mk_if_stmt: Internal error - else_result has wrong type {type(else_result_node)}")
             if isinstance(else_result_node, list) and not all(isinstance(s, ast.Statement) for s in else_result_node): raise TypeError("mk_if_stmt: Else block list contains non-Statements")
        return ast.IfStmt(condition=cond_node, then_block=then_block, else_block=else_result_node)
    def else_clause(self, items: List) -> Union[ast.IfStmt, List[ast.Statement]]:
         content_item_or_list = items[1:]
         first_content = content_item_or_list[0] if content_item_or_list else None
         if isinstance(first_content, ast.IfStmt): return first_content
         elif isinstance(first_content, Tree) and first_content.data == 'if_stmt': return self.mk_if_stmt(first_content.children)
         else: return self._collect_statements(content_item_or_list)
    def mk_while_stmt(self, items: List) -> ast.WhileStmt:
        cond_node = self._unwrap_expression_tree(items[1])
        body_block = self._collect_statements(items[2:-1])
        return ast.WhileStmt(condition=cond_node, body=body_block)
    def mk_loop_stmt(self, items: List) -> ast.LoopStmt:
        body_block = self._collect_statements(items[1:-1])
        return ast.LoopStmt(body=body_block)
        
    def mk_mem_block(self, items: List) -> ast.MemBlock:
        body_block = self._collect_statements(items[1:-1])
        return ast.MemBlock(body=body_block)
        
    def mk_e_mem_block(self, items: List) -> ast.EMemBlock: # <--- NOVO MÉTODO
        # items: [KW_E_MEM, Statement*, KW_END]
        # O último item é KW_END, então coletamos de items[1] até items[-2]
        body_block = self._collect_statements(items[1:-1])
        return ast.EMemBlock(body=body_block)

    # --- Handler genérico para expressões binárias ---
    def bin_op_expr(self, items: List) -> ast.Expression:
        # items já devem ser nós AST devido à precedência ou chamadas recursivas
        if len(items) == 1: return items[0]
        elif len(items) >= 3: return self._build_binary_op_tree(items) # Reusa o helper original
        else: raise ValueError(f"bin_op_expr unexpected items: {items}")

    def mk_cast_expr(self, items: List) -> ast.Expression:
        # items: [unary_expr_node] OU [unary_expr_node, KW_AS_token, type_node]
        base_expr = items[0]
        if not isinstance(base_expr, ast.Expression): raise TypeError("mk_cast_expr: base expr not Expression node")
        if len(items) == 3:
             target_type_node = items[2]
             if not isinstance(target_type_node, ast.Type): raise TypeError("mk_cast_expr: target_type not Type")
             return ast.CastExpr(expr=base_expr, target_type=target_type_node)
        return base_expr

    def mk_unary_op(self, items) -> ast.Expression:
        op_token = items[0]; op_str = ""

        # Lida com o caso especial '&mut' primeiro
        if op_token.type == 'AMPERSAND' and len(items) == 3 and isinstance(items[1], Token) and items[1].type == 'MUT':
            op_str = '&mut'
            operand_intermediate = items[2] # Operando é o terceiro
        else:
            # Mapeia tokens para operadores string
            # Inclui TILDE para ~
            op_map = {'BANG': '!', 'MINUS': '-', 'STAR': '*', 'AMPERSAND': '&', 'TILDE': '~'}
            op_str = op_map.get(op_token.type)
            if op_str is None:
                raise ValueError(f"Operador unário desconhecido no token: {op_token!r}")
            operand_intermediate = items[1] # Operando é o segundo

        # Desempacota o operando
        operand = self._unwrap_expression_tree(operand_intermediate)
        if not isinstance(operand, ast.Expression):
             raise TypeError(f"mk_unary_op: operando não é Expression node após unwrap: {type(operand)}")

        return ast.UnaryOp(op=op_str, operand=operand)

    def postfix_expr(self, items) -> ast.Expression:
        # items: [PrimaryExpr(Node/Tree/Token), Suffix(Tuple)*]
        # Garante que a base é uma expressão antes de aplicar sufixos
        current_expr = self._unwrap_expression_tree(items[0])
        if not isinstance(current_expr, ast.Expression):
            raise TypeError(f"postfix_expr: base expr is not Expression after unwrap, got {type(current_expr)}")

        # print(f"DEBUG Parser: postfix_expr - Base: {current_expr!r}") # DEBUG

        # Aplica sufixos
        for suffix_data in items[1:]:
            if suffix_data is None: continue # Pode acontecer?

            # Verifica se suffix_data é a tupla esperada
            if not isinstance(suffix_data, tuple) or len(suffix_data) != 2:
                 print(f"ERROR: postfix_expr recebeu sufixo inválido: {suffix_data!r}")
                 continue # Pula sufixo inválido

            suffix_type, suffix_value = suffix_data
            # print(f"  DEBUG Parser: Aplicando sufixo: Tipo={suffix_type}, Valor={suffix_value!r}") # DEBUG

            if suffix_type == "call":
                if not isinstance(suffix_value, list): raise TypeError(f"call suffix value not list: {suffix_value!r}")
                # Cria o nó FunctionCall
                current_expr = ast.FunctionCall(callee=current_expr, args=suffix_value)
                # print(f"    DEBUG Parser: Result after call: {current_expr!r}") # DEBUG
            elif suffix_type == "index":
                if not isinstance(suffix_value, ast.Expression): raise TypeError(f"index suffix value not Expression: {suffix_value!r}")
                current_expr = ast.IndexAccess(array=current_expr, index=suffix_value)
                # print(f"    DEBUG Parser: Result after index: {current_expr!r}") # DEBUG
            elif suffix_type == "field":
                if not isinstance(suffix_value, ast.Identifier): raise TypeError(f"field suffix value not Identifier: {suffix_value!r}")
                current_expr = ast.FieldAccess(obj=current_expr, field=suffix_value)
                # print(f"    DEBUG Parser: Result after field: {current_expr!r}") # DEBUG
            else:
                raise ValueError(f"Tipo de sufixo postfix desconhecido: '{suffix_type}'")

        # print(f"DEBUG Parser: postfix_expr - Final: {current_expr!r}") # DEBUG
        return current_expr
        
    def mk_underscore(self, _) -> ast.Underscore: return ast.Underscore()
    def mk_array_repeat_expr(self, items: List) -> ast.ArrayRepeatExpr:
        # items: [Token('['), Expression|Tree|Token, Token(';'), Expression|Tree|Token, Token(']')]
        value_intermediate = items[1]
        size_intermediate = items[3]

        # Garante que valor e tamanho são nós Expression
        value_node = self._unwrap_expression_tree(value_intermediate)
        size_node = self._unwrap_expression_tree(size_intermediate)

        if not isinstance(value_node, ast.Expression):
             raise TypeError(f"mk_array_repeat_expr: value not Expression after unwrap, got {type(value_node)}")
        if not isinstance(size_node, ast.Expression):
             raise TypeError(f"mk_array_repeat_expr: size not Expression after unwrap, got {type(size_node)}")

        return ast.ArrayRepeatExpr(value=value_node, size=size_node)
    def mk_namespace_access(self, items: List) -> ast.NamespaceAccess:
        namespace_ident = items[0]; item_ident = items[2]
        if not isinstance(namespace_ident, ast.Identifier): raise TypeError("namespace_access: namespace not Identifier")
        if not isinstance(item_ident, ast.Identifier): raise TypeError("namespace_access: item not Identifier")
        return ast.NamespaceAccess(namespace=namespace_ident, item=item_ident)
        
    def mk_call_suffix(self, items: List) -> tuple:
        # items: [ Token('('), arg_part(Tree('arg_list',...) | Tree('expression',...) | None), Token(')') ]
        # print(f"DEBUG Parser: mk_call_suffix - items recebidos: {items!r}")
        args = []
        arg_part = items[1] # O item entre os parênteses

        if isinstance(arg_part, list):
             # Caso 1: arg_list retornou diretamente a lista (múltiplos argumentos)
             args = arg_part
             if not all(isinstance(a, ast.Expression) for a in args):
                  raise TypeError(f"mk_call_suffix: arg_list retornou lista inválida: {args}")
        elif isinstance(arg_part, Tree):
             # Caso 2: Apenas um argumento, pode vir como Tree('expression', ...)
             if arg_part.data == 'expression':
                 # Desembrulha a expressão única
                 single_arg = self._unwrap_expression_tree(arg_part)
                 if isinstance(single_arg, ast.Expression):
                     args = [single_arg] # Cria lista com o único argumento
                 else:
                     print(f"WARN: mk_call_suffix não conseguiu desembrulhar argumento único: {arg_part!r}")
             # Caso 3: Pode ser Tree('arg_list', ...) se a gramática/Lark decidir assim
             elif arg_part.data == 'arg_list':
                 args = self.arg_list(arg_part.children) # Chama arg_list nos filhos
             else:
                  print(f"WARN: mk_call_suffix recebeu Tree inesperada: {arg_part!r}. Assumindo 0 args.")
        elif arg_part is None:
             # Caso 4: Chamada vazia ()
             args = []
        else:
             print(f"WARN: mk_call_suffix estrutura inesperada para parte do argumento: {type(arg_part)}. Assumindo 0 args.")
             args = []

        # print(f"DEBUG Parser: mk_call_suffix - args finais: {args!r}")
        return ("call", args)
    def mk_index_suffix(self, items: List) -> tuple:
        # items: [Token('['), Expression|Tree|Token, Token(']')]
        index_intermediate = items[1]
        index_expr = self._unwrap_expression_tree(index_intermediate) # <-- ADICIONAR UNWRAP
        if not isinstance(index_expr, ast.Expression): # <-- Validar DEPOIS do unwrap
            raise TypeError(f"mk_index_suffix: index not Expression after unwrap, got {type(index_expr)}")
        return ("index", index_expr)
    def mk_field_suffix(self, items: List) -> tuple:
        # items: [Token('.'), Identifier | Token(CNAME)]
        fld_node = items[1]
        if isinstance(fld_node, Token) and fld_node.type == 'CNAME':
             fld_node = self.mk_identifier(fld_node) # Transforma CNAME se necessário
        elif not isinstance(fld_node, ast.Identifier):
             # Tentar desempacotar se for uma Tree inesperada (menos provável aqui)
             fld_node = self._unwrap_expression_tree(fld_node)

        if not isinstance(fld_node, ast.Identifier):
             raise TypeError(f"mk_field_suffix: field is not Identifier, got {type(fld_node)}")
        return ("field", fld_node)
    def array_element_list(self, items: List) -> List[ast.Expression]:
        # Esta função recebe a lista de expressões e vírgulas
        elements = []
        for item in items:
            # --- CORREÇÃO AQUI ---
            # Pula os tokens de vírgula diretamente
            if isinstance(item, Token) and item.type == 'COMMA':
                continue
            # --- FIM CORREÇÃO ---

            # Tenta desembrulhar os outros itens (devem ser expressões ou árvores)
            try:
                # Desembrulha o item para garantir que seja uma expressão
                unwrapped_item = self._unwrap_expression_tree(item)
                if isinstance(unwrapped_item, ast.Expression):
                    elements.append(unwrapped_item)
                # Ignora outros possíveis nós/None que _unwrap não converteu para Expr
                elif unwrapped_item is not None: # Não reclama de None
                    print(f"WARN: array_element_list ignorou item inesperado (após unwrap): {type(unwrapped_item)}")
            except TypeError as e:
                 # Captura erro do _unwrap se ele não conseguir converter algo inesperado
                 print(f"WARN: array_element_list encontrou erro ao desembrulhar: {e}. Item original: {item!r}")
            except Exception as e_unwrap: # Captura outros erros
                 print(f"WARN: array_element_list encontrou erro inesperado ao desembrulhar: {e_unwrap}. Item original: {item!r}")

        return elements
    def mk_array_literal(self, items: List) -> ast.ArrayLiteral:
        # items: [ Token('['), array_element_list(List[Expr]) | None, Token(']') ]
        # print(f"DEBUG Parser: mk_array_literal - items recebidos: {items!r}") # DEBUG
        elements = []
        if len(items) > 2 and isinstance(items[1], list):
             # Assume que items[1] é o resultado de array_element_list
             elements = items[1]
             # Verifica se a lista contém apenas Expressions
             if not all(isinstance(el, ast.Expression) for el in elements):
                  raise TypeError(f"mk_array_literal: resultado de array_element_list não contém apenas Expressions: {elements}")
        elif len(items) == 2: # Apenas '[' e ']'
             elements = []
        else:
             print(f"WARN: mk_array_literal estrutura inesperada: {items!r}. Assumindo array vazio.")
             elements = []

        # print(f"DEBUG Parser: mk_array_literal - elementos finais: {elements!r}") # DEBUG
        return ast.ArrayLiteral(elements=elements)
        
    def struct_literal_field_list(self, items: List) -> List[ast.StructLiteralField]:
        # print(f"\nDEBUG TRANSFORMER: struct_literal_field_list (RAW ITEMS): len={len(items)}")
        # for i, item_raw in enumerate(items):
        #     print(f"  Raw items[{i}]: type={type(item_raw)}, value={item_raw!r}")
        
        fields = []
        for item_in_sflfl in items:
            if isinstance(item_in_sflfl, ast.StructLiteralField):
                fields.append(item_in_sflfl)
            elif isinstance(item_in_sflfl, Token) and item_in_sflfl.type == 'COMMA':
                pass 
            # else:
                # print(f"    WARN struct_literal_field_list: Ignorando item inesperado: type={type(item_in_sflfl)}, value={item_in_sflfl!r}")
        
        # print(f"  Campos filtrados (retornando de struct_literal_field_list): {fields!r}")
        return fields
        
    def mk_struct_literal(self, items: List) -> ast.StructLiteral:
        type_name_node_intermediate = items[0]
        
        # --- DEBUG INICIAL (MANTENHA SE QUISER, MAS O PROBLEMA ESTÁ ABAIXO) ---
        # print(f"\nDEBUG TRANSFORMER: mk_struct_literal (RAW ITEMS para {type_name_node_intermediate!r}): len={len(items)}")
        # for i, item_raw in enumerate(items):
        #     print(f"  Raw items[{i}]: type={type(item_raw)}, value={item_raw!r}")
        # --- FIM DEBUG INICIAL ---

        type_name_node: ast.Identifier
        if isinstance(type_name_node_intermediate, Token) and type_name_node_intermediate.type == 'CNAME':
            type_name_node = self.mk_identifier(type_name_node_intermediate)
        elif isinstance(type_name_node_intermediate, ast.Identifier):
            type_name_node = type_name_node_intermediate
        else: 
            unwrapped_type_name = self._unwrap_expression_tree(type_name_node_intermediate)
            if isinstance(unwrapped_type_name, ast.Identifier):
                type_name_node = unwrapped_type_name
            else:
                raise TypeError(f"mk_struct_literal: type_name não é Identifier, CNAME, ou Tree que resolve para Identifier. Got {type(type_name_node_intermediate)} (original) / {type(unwrapped_type_name)} (unwrapped)")

        # print(f"DEBUG TRANSFORMER: mk_struct_literal para nome de tipo '{type_name_node.name}':") # Movido para depois da transformação do nome

        actual_fields: List[ast.StructLiteralField] = []
        
        if len(items) == 4: # Esperado: type_name, LBRACE, field_list_or_single_field, RBRACE
            fields_from_rule = items[2] 
            # print(f"  len(items) == 4. Conteúdo de items[2] (fields_from_rule): type={type(fields_from_rule)}, value={fields_from_rule!r}")
            
            if isinstance(fields_from_rule, list): # Caso: Múltiplos campos (ou zero, se struct_literal_field_list retornou [])
                if all(isinstance(f, ast.StructLiteralField) for f in fields_from_rule):
                    actual_fields = fields_from_rule
                # else: WARN/ERRO já impresso se a lista continha lixo
            
            # <=== NOVA CONDIÇÃO PARA CAMPO ÚNICO ===>
            elif isinstance(fields_from_rule, ast.StructLiteralField): 
                # Caso: Apenas um campo, Lark passou o StructLiteralField diretamente
                actual_fields = [fields_from_rule]
                print(f"    INFO mk_struct_literal: items[2] é um único StructLiteralField. Envolvendo em lista.")
            # <=== FIM NOVA CONDIÇÃO ===>

            elif fields_from_rule is None: 
                # print(f"    INFO mk_struct_literal: items[2] (fields_from_rule) é None. Usando lista de campos vazia.")
                actual_fields = [] 
            else: # Não é lista, nem StructLiteralField, nem None
                print(f"    WARN mk_struct_literal: items[2] (fields_from_rule) tipo inesperado {type(fields_from_rule)}. Usando lista de campos vazia.")
                actual_fields = []
            
        elif len(items) == 3: # Esperado: type_name, LBRACE, RBRACE (sem campos)
            # print(f"  len(items) == 3. Assumindo sem campos.")
            actual_fields = []
        else:
            print(f"  ERROR mk_struct_literal: Estrutura de 'items' inesperada. Len={len(items)}. Usando lista de campos vazia como fallback, mas isso é um erro.")
            actual_fields = []
            
        # print(f"  Final actual_fields para '{type_name_node.name}': {actual_fields!r}")
        return ast.StructLiteral(type_name=type_name_node, fields=actual_fields)

    # struct_literal_field_list e mk_struct_literal_field permanecem como na sua última versão correta.
    # Apenas certifique-se de que a linha "return items[1]" foi removida de mk_struct_literal_field.
        
    def mk_struct_literal_field(self, items: List) -> ast.StructLiteralField:
        name_node_intermediate = items[0]
        value_intermediate = items[2] 

        name_node: ast.Identifier
        if isinstance(name_node_intermediate, Token) and name_node_intermediate.type == 'CNAME':
            name_node = self.mk_identifier(name_node_intermediate)
        elif isinstance(name_node_intermediate, ast.Identifier):
            name_node = name_node_intermediate
        else: 
            unwrapped_name = self._unwrap_expression_tree(name_node_intermediate)
            if isinstance(unwrapped_name, ast.Identifier):
                name_node = unwrapped_name
            else:
                raise TypeError(f"mk_struct_literal_field: name não é Identifier, CNAME, ou Tree que resolve para Identifier. Got {type(name_node_intermediate)} (original) / {type(unwrapped_name)} (unwrapped)")

        value_node = self._unwrap_expression_tree(value_intermediate)
        if not isinstance(value_node, ast.Expression):
            raise TypeError(f"mk_struct_literal_field: value não é Expression após unwrap, got {type(value_node)}")

        created_field = ast.StructLiteralField(name=name_node, value=value_node)
        return created_field
    
    # Adiciona os novos terminais
    def TILDE(self, t): return t
    def PIPE(self, t): return t
    def CARET(self, t): return t
    def LSHIFT(self, t): return t
    def RSHIFT(self, t): return t
    # AMPERSAND já existe

    # Os novos métodos de regra binária podem simplesmente chamar bin_op_expr
    # (Lark pode otimizar isso, ou podemos mapeá-los diretamente)
    def bitwise_or_expr(self, items): return self.bin_op_expr(items)
    def bitwise_xor_expr(self, items): return self.bin_op_expr(items)
    def bitwise_and_expr(self, items): return self.bin_op_expr(items)
    def shift_expr(self, items): return self.bin_op_expr(items)


# --- Função Principal de Parsing ---
def parse_atom(code: str) -> ast.Program:
    parser = None
    try:
        # Tentar LALR primeiro com a gramática de precedência
        parser = Lark(atom_v02_grammar, start='program', parser='lalr', propagate_positions=True)
        print("DEBUG: Parser LALR (Precedence Grammar) criado.")
    except exceptions.LarkError as e_lalr: # Captura especificamente erros do LALR
         print(f"Falha ao criar parser LALR (provavelmente conflitos S/R ou R/R): {e_lalr}")
         print("Tentando com Earley como fallback...")
         try:
             parser = Lark(atom_v02_grammar, start='program', parser='earley', propagate_positions=True)
             print("DEBUG: Parser Earley (Precedence Grammar - Fallback) criado.")
         except Exception as e_earley_fallback:
             raise RuntimeError(f"Falha ao criar parser Earley (fallback): {e_earley_fallback}") from e_earley_fallback
    except Exception as e_parser_creation: # Captura outros erros de criação
         raise RuntimeError(f"Falha ao criar parser: {e_parser_creation}") from e_parser_creation

    try:
        parse_tree = parser.parse(code)
        print("DEBUG: Parsing concluído.")
    except exceptions.UnexpectedInput as e: # Captura especificamente UnexpectedInput
         context = e.get_context(code)
         # Para UnexpectedCharacters, e.allowed existe. Para outros, pode ser e.expected.
         # Fornece um fallback para um conjunto vazio se nenhum existir.
         expected_set = getattr(e, 'allowed', getattr(e, 'expected', set()))
         expected_tokens_str = ", ".join(sorted(list(expected_set))) if expected_set else "desconhecido"
         print(f"Erro de Parsing: Entrada inesperada na linha {e.line}, coluna {e.column}.\nEsperado (um de): {expected_tokens_str}\n--- Contexto ---\n{context}\n----------------")
         raise RuntimeError(f"Erro Parsing Lark: {e}") from e
    except Exception as e_parse: # Captura outros erros de parsing
        print(f"Erro durante o parsing do código:\n{code}")
        raise RuntimeError(f"Erro Parsing Lark: {e_parse}") from e_parse

    try:
        print("DEBUG: Iniciando transformação...")
        transformer = AtomTransformer() # Sem visit_tokens=True
        ast_tree = transformer.transform(parse_tree)
        print("DEBUG: Transformação concluída.")
    except exceptions.VisitError as e_visit:
        print(f"Erro durante a transformação visitando regra '{getattr(e_visit.rule, 'origin', e_visit.obj)}':")
        orig_exc = getattr(e_visit, 'orig_exc', e_visit)
        print(f"  Exceção original: {type(orig_exc).__name__}: {orig_exc}")
        meta = getattr(e_visit.obj, 'meta', None) if hasattr(e_visit, 'obj') else None
        if meta: print(f"  Próximo à linha {meta.line}, coluna {meta.column}")
        else: print("  (Localização exata incerta)")
        print("--- Detalhes do Erro de Transformação ---"); traceback.print_exc(); print("-----------------------------------------")
        raise RuntimeError(f"Erro Transformação Lark->AST: {e_visit}") from e_visit
    except Exception as e_transform:
        print(f"Erro inesperado durante a transformação:")
        print("--- Detalhes do Erro de Transformação ---"); traceback.print_exc(); print("-----------------------------------------")
        raise RuntimeError(f"Erro Transformação Lark->AST: {e_transform}") from e_transform

    if not isinstance(ast_tree, ast.Program): raise TypeError(f"Resultado final não é ast.Program: {type(ast_tree)}")
    return ast_tree


# --- Teste Final (Código Completo) ---
if __name__ == '__main__':
    final_test_code_end_syntax = r"""
    struct Vec2
    x: i32,
    y: i32,
	end
	
	struct MyData
		id: i32,
	end
	
	func process_slice(data_slice: &[MyData], empty_slice: &[i32]) -> usize
		let len1 = data_slice.len;
		let len2 = empty_slice.len; // Deve ser 0

		if len1 > (0 as usize)
		    let first_id = data_slice[0].id; // Acesso a elemento de slice e depois a campo
		    mem printf("First ID: %d\n", first_id); end
		end # Fim do if len1 > 0
		return len1 + len2;
	end # Fim de process_slice


	const SIZE: usize = 5;
	const ORIGIN: Vec2 = Vec2 { x: 0, y: 0 };

	# Bloco Extern com 'end'
	extern "C"
		func printf(*const char, ...) -> i32; # Função Varargs
		func puts(*const char) -> i32;
		# Assinatura correta com base na chamada no CodeGen:
		func atom_panic_bounds_check(usize, usize) -> ();
		func atom_do_bounds_check(usize, usize) -> ();
	end
	
	struct Entity
		pos: &mut Vec2,          # Referência mutável
		vel: Vec2,               # Valor struct
		tag: *const char,        # Ponteiro imutável
		sprite_ids: [u8; 4],     # Array
		neighbors: &[Entity],    # Slice imutável
	end

	# Enum com 'end' (C-Like por enquanto)
	enum State
		Idle,
		Running,
		Jumping,
	end

	# Função para teste de callback
	func my_callback_func(n: i32) -> bool
		if n > 0
		    return true;
		else
		    return false;
		end
	end

	# Definição de Função com 'end'
	func update_entity(e: &mut Entity, dt_scale_factor: i32) -> ()
		let move_x = (e.vel.x * dt_scale_factor) / (256 as i32);
		let _ = e.pos.x; # Ignora o valor lido
		return;
	end # Fim de update_entity
	
	func test_mem_no_scope() -> ()
    let x: i32 = 10;
    mem
        let y: i32 = x + 5; // y deve ser visível fora
        // ... operações inseguras ...
    end
    let z = y; // OK
	end
	
	func test_e_mem_with_scope() -> ()
    let x: i32 = 10;
    mut result: i32 = 0;
    e_mem
        let y_internal: i32 = x + 5; // y_internal NÃO deve ser visível fora
        result = y_internal * 2;
        // ... operações inseguras ...
    end
    // let w = y_internal; // ERRO: y_internal não definido aqui
    let final_val = result; // OK
	end

	func main() -> ()
		let score: i32 = (100 * 2 + 50) as i32;
		mut current_pos = Vec2 { x: 10, y: 20 };
		let static_msg: *const char = "Hello Atom!";
		let another_msg: *const char = "Uma linha simples.";

		# Array literal com structs e constante
		let points: [Vec2; 3] = [ Vec2{x:1, y:1}, ORIGIN, Vec2{x: -1, y:-1}, ];
		# Slice vazio (inicialização)
		let empty_entities: &[Entity] = &[];
		# Array repeat
		let default_sprites: [u8; 4] = [1 as u8; 4];

		let next_score = score / (2 as i32);
		# Operadores lógicos e acesso a campos
		let is_zero = current_pos.x == ORIGIN.x && current_pos.y == ORIGIN.y;
		# Acesso a índice e campo
		let first_pt_x = points[0].x;

		# Bloco mem
		mem
		     let temp_ptr = another_msg;
		     puts(temp_ptr);
		     printf("Hello %d\n", 123);
		end

		# Struct literal complexo
		mut player_entity = Entity {
		    pos: &mut current_pos,
		    vel: Vec2 { x: (5 * 256) as i32, y: 0 },
		    tag: static_msg,
		    sprite_ids: default_sprites,
		    neighbors: empty_entities,
		};

		# If/Else com 'end'
		if is_zero || first_pt_x < (0 as i32)
		    mem end
		else
		    mut i: i32 = 0;
		    # While loop
		    while i < (3 as i32)
		         let dummy = i + (1 as i32);
		         i = dummy;
		    end
		end
		
		# Testes Bitwise
		let flags: u8 = 0b1100_1010;
		let masked = flags & 0b0000_1111;
		let shifted = masked << 2;
		let inverted = ~flags;
		let combined = shifted | 1;
		let xor_test = combined ^ masked;

		# Teste Ponteiro de Função
		let cb: func(i32)->bool = my_callback_func;
		let is_pos = cb(10);
		let is_neg = cb(-5);

		let current_state: State = State::Running;
		let next_state: State = State::Idle;

		mem
		    printf("Current state: %d, Next state: %d\n",
		        current_state as u32,
		        next_state as u32);
		end

		if current_state == State::Running
		    mem printf("Entity is running!\n"); end
		end

		# Teste Byte String
		let my_bstr: &[u8] = b"Atom\x01\x02\x03";

		# --- Loops de teste --- <== MOVER DECLARAÇÕES PARA FORA SE QUISER USAR DEPOIS
		mut k_loop: i32 = 0; # Declarado fora do loop
		loop
		    k_loop = k_loop + 1;
		    if k_loop == 2
		        continue;
		    end
		    mem printf("Loop k: %d\n", k_loop as u32); end
		    if k_loop == 4
		        break;
		    end
		end
		# Agora k_loop é acessível aqui (se necessário)
		mem printf("Loop finalizado com k_loop: %d\n", k_loop as u32); end

		mut j_while: i32 = 0; # Declarado fora do loop
		while j_while < 5
		    j_while = j_while + 1;
		    if j_while == 3
		        mem printf("While j==3, continue\n"); end
		        continue;
		    end
		    if j_while == 5
		        mem printf("While j==5, break\n"); end
		        break;
		    end
		    mem printf("While j: %d\n", j_while as u32); end
		end
		# Agora j_while é acessível aqui
		mem printf("While finalizado com j_while: %d\n", j_while as u32); end
		# --- Fim Loops ---

		# Chamadas printf finais
		mem
		    printf("Masked: %u, Shifted: %u, Combined: %u, Inverted: %u, XOR: %u\n",
		           masked as u32, shifted as u32, combined as u32, inverted as u32, xor_test as u32);
		end

		mem
		    printf("Callback results: %u, %u\n", is_pos as u32, is_neg as u32);
		end

		# --- Definições para os testes de bounds check ---
		let d1 = MyData { id: 10 };
		let d2 = MyData { id: 20 };
		let d3 = MyData { id: 30 };

		let my_array: [MyData; 3] = [d1, d2, d3]; # Tamanho 3
		let a_slice: &[MyData] = &my_array;      # len = 3
		let another_slice: &[MyData] = a_slice;
		let empty: &[i32] = &[];

		let res = process_slice(another_slice, empty);
		mem printf("Total len from process_slice: %lu\n", res as u64); end

		mut mut_array: [i32; 2] = [100, 200]; # Tamanho 2
		let mut_s: &mut [i32] = &mut mut_array; # len = 2

		let b_str_slice: &[u8] = b"hello"; # len = 5

		let my_bytes_test: &[u8] = b"Data"; # len = 4

		# --- TESTES DE BOUNDS CHECKING ---
		# Objetivo: Estas linhas DEVEM causar pânico em tempo de execução

		# Teste com slice '&[MyData]' (a_slice, len=3)
		mem printf("Tentando acessar a_slice[3] (fora)...\n"); end
		a_slice[3]; # Deve dar pânico (índice == len)

		mem printf("Tentando acessar a_slice[5] (fora)...\n"); end
		a_slice[5]; # Deve dar pânico (índice > len)

		# Teste com slice '&mut [i32]' (mut_s, len=2)
		mem printf("Tentando acessar mut_s[2] (fora)...\n"); end
		mut_s[2] = 500; # Deve dar pânico (índice == len)

		# Teste com slice '&[u8]' (b_str_slice, len=5)
		mem printf("Tentando acessar b_str_slice[5] (fora)...\n"); end
		b_str_slice[5]; # Deve dar pânico (índice == len)

		# Teste com array '[MyData; 3]' (my_array)
		mem printf("Tentando acessar my_array[3] (fora)...\n"); end
		my_array[3]; # Deve dar pânico (índice == N)

		# Esta linha não deve ser alcançada se o pânico funcionar
		mem printf("Bounds check tests concluídos (se não houve pânico, algo está errado).\n"); end
		# --- FIM DOS TESTES ---

		

    
		return;
	end # Fim de main
		"""

    print(f"Analisando código de teste final (Precedence Grammar):\n{final_test_code_end_syntax}")
    final_ast = None
    try:
        final_ast = parse_atom(final_test_code_end_syntax)
        print("\nAST gerada com sucesso!")

        # (Restante das etapas)
        print("\n--- Iniciando Análise Semântica ---");
        try:
            semantic_errors = analyze_semantics(final_ast)
            if not semantic_errors: print("Análise semântica concluída sem erros.")
            else: print(f"\n{len(semantic_errors)} Erros Semânticos:"); [print(f"- {e}") for e in semantic_errors]; raise ValueError("Erros semânticos.")
        except ImportError: print("\nAVISO: semantic_analyzer.py não encontrado.")
        except Exception as e_semantic: print(f"\nErro Análise Semântica: {e_semantic}"); traceback.print_exc(); raise

        print("\n--- Iniciando Geração de Código LLVM IR ---");
        try:
            llvm_ir = generate_llvm_ir(final_ast)
            print("\n--- LLVM IR Gerado ---"); print(llvm_ir); print("----------------------")
            with open("output_precedence.ll", "w") as f: f.write(llvm_ir)
            print("LLVM IR salvo em output_precedence.ll")
        except ImportError: print("\nAVISO: codegen_llvm.py não encontrado.")
        except Exception as e_codegen: print(f"\nErro Geração de Código: {e_codegen}"); traceback.print_exc(); raise

    except exceptions.VisitError as e_visit:
        print(f"\nErro durante transformação (VisitError): {e_visit}")
        traceback.print_exc()
    except Exception as e:
        print(f"\nErro ao processar código: {e}")
        traceback.print_exc()
    finally:
        print("\nProcessamento concluído.")
