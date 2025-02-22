#!/usr/bin/env python
# License: GPLv3 Copyright: 2010, Kovid Goyal <kovid at kovidgoyal.net>

import copy, json, traceback
from qt.core import QDialogButtonBox, QDialog

from calibre.gui2 import error_dialog, warning_dialog
from calibre.gui2.dialogs.template_dialog import TemplateDialog
from calibre.gui2.preferences import ConfigWidgetBase, test_widget
from calibre.gui2.preferences.template_functions_ui import Ui_Form
from calibre.gui2.widgets import PythonHighlighter
from calibre.utils.formatter_functions import (
    compile_user_function, compile_user_template_functions, formatter_functions,
    function_pref_is_python, function_pref_name, load_user_template_functions
)
from polyglot.builtins import iteritems, native_string_type, unicode_type


class ConfigWidget(ConfigWidgetBase, Ui_Form):

    def genesis(self, gui):
        self.gui = gui
        self.db = gui.library_view.model().db

        help_text = _('''
        <p>Here you can add and remove functions used in template processing. A
        template function is written in Python. It takes information from the
        book, processes it in some way, then returns a string result. Functions
        defined here are usable in templates in the same way that builtin
        functions are usable. The function must be named <b>evaluate</b>, and
        must have the signature shown below.</p>
        <p><code>evaluate(self, formatter, kwargs, mi, locals, your parameters)
        &rarr; returning a Unicode string</code></p>
        <p>The parameters of the evaluate function are:
        <ul>
        <li><b>formatter</b>: the instance of the formatter being used to
        evaluate the current template. You can use this to do recursive
        template evaluation.</li>
        <li><b>kwargs</b>: a dictionary of metadata. Field values are in this
        dictionary.</li>
        <li><b>mi</b>: a <i>Metadata</i> instance. Used to get field information.
        This parameter can be None in some cases, such as when evaluating
        non-book templates.</li>
        <li><b>locals</b>: the local variables assigned to by the current
        template program.</li>
        <li><b>your parameters</b>: you must supply one or more formal
        parameters. The number must match the arg count box, unless arg count is
        -1 (variable number or arguments), in which case the last argument must
        be *args. At least one argument is required, and is usually the value of
        the field being operated upon. Note that when writing in basic template
        mode, the user does not provide this first argument. Instead it is
        supplied by the formatter.</li>
        </ul></p>
        <p>
        The following example function checks the value of the field. If the
        field is not empty, the field's value is returned, otherwise the value
        EMPTY is returned.
        <pre>
        name: my_ifempty
        arg count: 1
        doc: my_ifempty(val) -- return val if it is not empty, otherwise the string 'EMPTY'
        program code:
        def evaluate(self, formatter, kwargs, mi, locals, val):
            if val:
                return val
            else:
                return 'EMPTY'</pre>
        This function can be called in any of the three template program modes:
        <ul>
        <li>single-function mode: {tags:my_ifempty()}</li>
        <li>template program mode: {tags:'my_ifempty($)'}</li>
        <li>general program mode: program: my_ifempty(field('tags'))</li>
        </p>
        ''')
        self.textBrowser.setHtml(help_text)
        self.textBrowser_showing = True
        self.textBrowser.adjustSize()
        self.show_hide_help_button.clicked.connect(self.show_hide_help)
        help_text = _('''
        <p>
        Here you can create, edit (replace), and delete stored templates used
        in template processing. You use a stored template in another template as
        if it were a template function, for example 'some_name(arg1, arg2...)'.</p>

        <p>Stored templates must use General Program Mode -- they must begin with
        the text '{0}'. You retrieve arguments passed to a stored template using
        the '{1}()' template function, as in '{1}(var1, var2, ...)'. The passed
        arguments are copied to the named variables.</p>

        <p>For example, this stored template checks if any items are in a
        list, returning '1' if any are found and '' if not.</p>
        <p>
        Template name: items_in_list<br>
        Template contents:<pre>
        program:
            arguments(lst='No list argument given', items='');
            r = '';
            for l in items:
                if str_in_list(lst, ',', l, '1', '') then
                    r = '1';
                    break
                fi
            rof;
            r</pre>
        You call the stored template like this:<pre>
        program: items_in_list($#genre, 'comics, foo')</pre>
        See the template language tutorial for more information.</p>
        </p>
        ''')
        self.st_textBrowser.setHtml(help_text.format('program:', 'arguments'))
        self.st_textBrowser_showing = True
        self.st_textBrowser.adjustSize()
        self.st_show_hide_help_button.clicked.connect(self.st_show_hide_help)

    def st_show_hide_help(self):
        if self.st_textBrowser_showing:
            self.st_textBrowser_height = self.st_textBrowser.height()
            self.st_textBrowser.setMaximumHeight(self.st_show_hide_help_button.height())
            self.st_textBrowser_showing = False
            self.st_show_hide_help_button.setText(_('Show help'))
        else:
            self.st_textBrowser.setMaximumHeight(self.st_textBrowser_height)
            self.st_textBrowser_showing = True
            self.st_show_hide_help_button.setText(_('Hide help'))

    def show_hide_help(self):
        if self.textBrowser_showing:
            self.textBrowser_height = self.textBrowser.height()
            self.textBrowser.setMaximumHeight(self.show_hide_help_button.height())
            self.textBrowser_showing = False
            self.show_hide_help_button.setText(_('Show help'))
        else:
            self.textBrowser.setMaximumHeight(self.textBrowser_height)
            self.textBrowser_showing = True
            self.show_hide_help_button.setText(_('Hide help'))

    def initialize(self):
        try:
            self.builtin_source_dict = json.loads(P('template-functions.json', data=True,
                allow_user_override=False).decode('utf-8'))
        except:
            traceback.print_exc()
            self.builtin_source_dict = {}

        self.funcs = {k:v for k,v in formatter_functions().get_functions().items()
                                if v.is_python}

        self.builtins = formatter_functions().get_builtins_and_aliases()

        self.st_funcs = {}
        for v in self.db.prefs.get('user_template_functions', []):
            if not function_pref_is_python(v):
                self.st_funcs.update({function_pref_name(v):compile_user_function(*v)})

        self.build_function_names_box()
        self.function_name.currentIndexChanged[native_string_type].connect(self.function_index_changed)
        self.function_name.editTextChanged.connect(self.function_name_edited)
        self.argument_count.valueChanged.connect(self.enable_replace_button)
        self.documentation.textChanged.connect(self.enable_replace_button)
        self.program.textChanged.connect(self.enable_replace_button)
        self.create_button.clicked.connect(self.create_button_clicked)
        self.delete_button.clicked.connect(self.delete_button_clicked)
        self.create_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.replace_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_button_clicked)
        self.replace_button.clicked.connect(self.replace_button_clicked)
        self.program.setTabStopWidth(20)
        self.highlighter = PythonHighlighter(self.program.document())

        self.te_textbox = self.template_editor.textbox
        self.te_name = self.template_editor.template_name
        self.st_build_function_names_box()
        self.te_name.currentIndexChanged[native_string_type].connect(self.st_function_index_changed)
        self.te_name.editTextChanged.connect(self.st_template_name_edited)
        self.st_create_button.clicked.connect(self.st_create_button_clicked)
        self.st_delete_button.clicked.connect(self.st_delete_button_clicked)
        self.st_create_button.setEnabled(False)
        self.st_delete_button.setEnabled(False)
        self.st_replace_button.setEnabled(False)
        self.st_test_template_button.setEnabled(False)
        self.st_clear_button.clicked.connect(self.st_clear_button_clicked)
        self.st_test_template_button.clicked.connect(self.st_test_template)
        self.st_replace_button.clicked.connect(self.st_replace_button_clicked)

        self.st_current_program_name = ''
        self.st_current_program_text = ''
        self.st_previous_text = ''
        self.st_first_time = False

        self.st_button_layout.insertSpacing(0, 90)
        self.template_editor.new_doc.setFixedHeight(50)

        # get field metadata and selected books
        view = self.gui.current_view()
        rows = view.selectionModel().selectedRows()
        self.mi = []
        if rows:
            db = view.model().db
            self.fm = db.field_metadata
            for row in rows:
                if row.isValid():
                    self.mi.append(db.new_api.get_proxy_metadata(db.data.index_to_id(row.row())))

            self.template_editor.set_mi(self.mi[0], self.fm)

    # Python function tab

    def enable_replace_button(self):
        self.replace_button.setEnabled(self.delete_button.isEnabled())

    def clear_button_clicked(self):
        self.build_function_names_box()
        self.program.clear()
        self.documentation.clear()
        self.argument_count.clear()
        self.create_button.setEnabled(False)
        self.delete_button.setEnabled(False)

    def build_function_names_box(self, scroll_to=''):
        self.function_name.blockSignals(True)
        func_names = sorted(self.funcs)
        self.function_name.clear()
        self.function_name.addItem('')
        self.function_name.addItems(func_names)
        self.function_name.setCurrentIndex(0)
        self.function_name.blockSignals(False)
        if scroll_to:
            idx = self.function_name.findText(scroll_to)
            if idx >= 0:
                self.function_name.setCurrentIndex(idx)
                if scroll_to not in self.builtins:
                    self.delete_button.setEnabled(True)

    def delete_button_clicked(self):
        name = unicode_type(self.function_name.currentText())
        if name in self.builtins:
            error_dialog(self.gui, _('Template functions'),
                         _('You cannot delete a built-in function'), show=True)
        if name in self.funcs:
            del self.funcs[name]
            self.changed_signal.emit()
            self.create_button.setEnabled(True)
            self.delete_button.setEnabled(False)
            self.build_function_names_box()
            self.program.setReadOnly(False)
        else:
            error_dialog(self.gui, _('Template functions'),
                         _('Function not defined'), show=True)

    def create_button_clicked(self, use_name=None):
        self.changed_signal.emit()
        name = use_name if use_name else unicode_type(self.function_name.currentText())
        if name in self.funcs:
            error_dialog(self.gui, _('Template functions'),
                         _('Name %s already used')%(name,), show=True)
            return
        if name in {function_pref_name(v) for v in
                        self.db.prefs.get('user_template_functions', [])
                        if not function_pref_is_python(v)}:
            error_dialog(self.gui, _('Template functions'),
                         _('The name {} is already used for stored template').format(name), show=True)
            return
        if self.argument_count.value() == 0:
            box = warning_dialog(self.gui, _('Template functions'),
                         _('Argument count should be -1 or greater than zero. '
                           'Setting it to zero means that this function cannot '
                           'be used in single function mode.'), det_msg='',
                         show=False, show_copy_button=False)
            box.bb.setStandardButtons(box.bb.standardButtons() | QDialogButtonBox.StandardButton.Cancel)
            box.det_msg_toggle.setVisible(False)
            if not box.exec_():
                return
        try:
            prog = unicode_type(self.program.toPlainText())
            cls = compile_user_function(name, unicode_type(self.documentation.toPlainText()),
                                        self.argument_count.value(), prog)
            self.funcs[name] = cls
            self.build_function_names_box(scroll_to=name)
        except:
            error_dialog(self.gui, _('Template functions'),
                         _('Exception while compiling function'), show=True,
                         det_msg=traceback.format_exc())

    def function_name_edited(self, txt):
        self.documentation.setReadOnly(False)
        self.argument_count.setReadOnly(False)
        self.create_button.setEnabled(True)
        self.replace_button.setEnabled(False)
        self.program.setReadOnly(False)

    def function_index_changed(self, txt):
        txt = unicode_type(txt)
        self.create_button.setEnabled(False)
        if not txt:
            self.argument_count.clear()
            self.documentation.clear()
            self.documentation.setReadOnly(False)
            self.argument_count.setReadOnly(False)
            return
        func = self.funcs[txt]
        self.argument_count.setValue(func.arg_count)
        self.documentation.setText(func.doc)
        if txt in self.builtins:
            if hasattr(func, 'program_text') and func.program_text:
                self.program.setPlainText(func.program_text)
            elif txt in self.builtin_source_dict:
                self.program.setPlainText(self.builtin_source_dict[txt])
            else:
                self.program.setPlainText(_('function source code not available'))
            self.documentation.setReadOnly(True)
            self.argument_count.setReadOnly(True)
            self.program.setReadOnly(True)
            self.delete_button.setEnabled(False)
        else:
            self.program.setPlainText(func.program_text)
            self.delete_button.setEnabled(True)
            self.program.setReadOnly(False)
        self.replace_button.setEnabled(False)

    def replace_button_clicked(self):
        name = unicode_type(self.function_name.currentText())
        self.delete_button_clicked()
        self.create_button_clicked(use_name=name)

    def refresh_gui(self, gui):
        pass

    # Stored template tab

    def st_test_template(self):
        if self.mi:
            self.st_replace_button_clicked()
            all_funcs = copy.copy(formatter_functions().get_functions())
            for n,f in self.st_funcs.items():
                all_funcs[n] = f
            t = TemplateDialog(self.gui, self.st_previous_text,
                   mi=self.mi, fm=self.fm, text_is_placeholder=self.st_first_time,
                   all_functions=all_funcs)
            t.setWindowTitle(_('Template tester'))
            if t.exec_() == QDialog.DialogCode.Accepted:
                self.st_previous_text = t.rule[1]
                self.st_first_time = False
        else:
            error_dialog(self.gui, _('Template functions'),
                         _('Cannot "test" when no books are selected'), show=True)

    def st_clear_button_clicked(self):
        self.st_build_function_names_box()
        self.te_textbox.clear()
        self.template_editor.new_doc.clear()
        self.st_create_button.setEnabled(False)
        self.st_delete_button.setEnabled(False)

    def st_build_function_names_box(self, scroll_to=''):
        self.te_name.blockSignals(True)
        func_names = sorted(self.st_funcs)
        self.te_name.setMinimumContentsLength(40)
        self.te_name.clear()
        self.te_name.addItem('')
        self.te_name.addItems(func_names)
        self.te_name.setCurrentIndex(0)
        self.te_name.blockSignals(False)
        if scroll_to:
            idx = self.te_name.findText(scroll_to)
            if idx >= 0:
                self.te_name.setCurrentIndex(idx)

    def st_delete_button_clicked(self):
        name = unicode_type(self.te_name.currentText())
        if name in self.st_funcs:
            del self.st_funcs[name]
            self.changed_signal.emit()
            self.st_create_button.setEnabled(True)
            self.st_delete_button.setEnabled(False)
            self.st_build_function_names_box()
            self.te_textbox.setReadOnly(False)
            self.st_current_program_name = ''
        else:
            error_dialog(self.gui, _('Stored templates'),
                         _('Function not defined'), show=True)

    def st_create_button_clicked(self, use_name=None):
        self.changed_signal.emit()
        name = use_name if use_name else unicode_type(self.te_name.currentText())
        for k,v in formatter_functions().get_functions().items():
            if k == name and v.is_python:
                error_dialog(self.gui, _('Stored templates'),
                         _('The name {} is already used for template function').format(name), show=True)
        try:
            prog = unicode_type(self.te_textbox.toPlainText())
            if not prog.startswith('program:'):
                error_dialog(self.gui, _('Stored templates'),
                         _('The stored template must begin with "program:"'), show=True)

            cls = compile_user_function(name, unicode_type(self.template_editor.new_doc.toPlainText()),
                                        0, prog)
            self.st_funcs[name] = cls
            self.st_build_function_names_box(scroll_to=name)
        except:
            error_dialog(self.gui, _('Stored templates'),
                         _('Exception while storing template'), show=True,
                         det_msg=traceback.format_exc())

    def st_template_name_edited(self, txt):
        b = txt in self.st_funcs
        self.st_create_button.setEnabled(not b)
        self.st_replace_button.setEnabled(b)
        self.st_delete_button.setEnabled(b)
        self.st_test_template_button.setEnabled(b)
        self.te_textbox.setReadOnly(False)

    def st_function_index_changed(self, txt):
        txt = unicode_type(txt)
        if self.st_current_program_name:
            if self.st_current_program_text != self.te_textbox.toPlainText():
                box = warning_dialog(self.gui, _('Template functions'),
                         _('Changes to the current template will be lost. OK?'), det_msg='',
                         show=False, show_copy_button=False)
                box.bb.setStandardButtons(box.bb.standardButtons() |
                                          QDialogButtonBox.StandardButton.Cancel)
                box.det_msg_toggle.setVisible(False)
                if not box.exec_():
                    self.te_name.blockSignals(True)
                    dex = self.te_name.findText(self.st_current_program_name)
                    self.te_name.setCurrentIndex(dex)
                    self.te_name.blockSignals(False)
                    return
        self.st_create_button.setEnabled(False)
        self.st_current_program_name = txt
        if not txt:
            self.te_textbox.clear()
            self.template_editor.new_doc.clear()
            return
        func = self.st_funcs[txt]
        self.st_current_program_text = func.program_text
        self.template_editor.new_doc.setPlainText(func.doc)
        self.te_textbox.setPlainText(func.program_text)
        self.st_template_name_edited(txt)

    def st_replace_button_clicked(self):
        name = unicode_type(self.te_name.currentText())
        self.st_current_program_text = self.te_textbox.toPlainText()
        self.st_delete_button_clicked()
        self.st_create_button_clicked(use_name=name)

    def commit(self):
        pref_value = []
        for name, cls in iteritems(self.funcs):
            if name not in self.builtins:
                pref_value.append(cls.to_pref())
        for v in self.st_funcs.values():
            pref_value.append(v.to_pref())
        self.db.new_api.set_pref('user_template_functions', pref_value)
        funcs = compile_user_template_functions(pref_value)
        self.db.new_api.set_user_template_functions(funcs)
        self.gui.library_view.model().refresh()
        load_user_template_functions(self.db.library_id, [], funcs)
        return False


if __name__ == '__main__':
    from calibre import Application
    app = Application([])
    test_widget('Advanced', 'TemplateFunctions')
    del app
