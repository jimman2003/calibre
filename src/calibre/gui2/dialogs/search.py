__license__   = 'GPL v3'
__copyright__ = '2008, Kovid Goyal <kovid at kovidgoyal.net>'

import re, copy
from datetime import date

from qt.core import (
    QDialog, QDialogButtonBox, QFrame, QLabel, QComboBox, QIcon, QVBoxLayout, Qt,
    QSize, QHBoxLayout, QTabWidget, QLineEdit, QWidget, QGroupBox, QFormLayout,
    QSpinBox, QRadioButton
)

from calibre import strftime
from calibre.library.caches import CONTAINS_MATCH, EQUALS_MATCH
from calibre.gui2 import gprefs
from calibre.gui2.complete2 import EditWithComplete
from calibre.utils.icu import sort_key
from calibre.utils.config import tweaks
from calibre.utils.date import now
from calibre.utils.localization import localize_user_manual_link
from polyglot.builtins import unicode_type, range, map

box_values = {}
last_matchkind = CONTAINS_MATCH


# UI {{{
def init_dateop(cb):
    for op, desc in [
            ('=', _('equal to')),
            ('<', _('before')),
            ('>', _('after')),
            ('<=', _('before or equal to')),
            ('>=', _('after or equal to')),
    ]:
        cb.addItem(desc, op)


def current_dateop(cb):
    return unicode_type(cb.itemData(cb.currentIndex()) or '')


def create_msg_label(self):
    self.frame = f = QFrame(self)
    f.setFrameShape(QFrame.Shape.StyledPanel)
    f.setFrameShadow(QFrame.Shadow.Raised)
    f.l = l = QVBoxLayout(f)
    f.um_label = la = QLabel(_(
        "<p>You can also perform other kinds of advanced searches, for example checking"
        ' for books that have no covers, combining multiple search expression using Boolean'
        ' operators and so on. See <a href=\"%s\">The search interface</a> for more information.'
    ) % localize_user_manual_link('https://manual.calibre-ebook.com/gui.html#the-search-interface'))
    la.setMinimumSize(QSize(150, 0))
    la.setWordWrap(True)
    la.setOpenExternalLinks(True)
    l.addWidget(la)
    return f


def create_match_kind(self):
    self.cmk_label = la = QLabel(_("What &kind of match to use:"))
    self.matchkind = m = QComboBox(self)
    la.setBuddy(m)
    m.addItems([
        _("Contains: the word or phrase matches anywhere in the metadata field"),
        _("Equals: the word or phrase must match the entire metadata field"),
        _("Regular expression: the expression must match anywhere in the metadata field"),
    ])
    l = QHBoxLayout()
    l.addWidget(la), l.addWidget(m)
    return l


def create_button_box(self):
    self.bb = bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    self.clear_button = bb.addButton(_('&Clear'), QDialogButtonBox.ButtonRole.ResetRole)
    self.clear_button.clicked.connect(self.clear_button_pushed)
    bb.accepted.connect(self.accept)
    bb.rejected.connect(self.reject)
    return bb


def create_adv_tab(self):
    self.adv_tab = w = QWidget(self.tab_widget)
    self.tab_widget.addTab(w, _("A&dvanced search"))

    w.g1 = QGroupBox(_("Find entries that have..."), w)
    w.g2 = QGroupBox(_("But don't show entries that have..."), w)
    w.l = l = QVBoxLayout(w)
    l.addWidget(w.g1), l.addWidget(w.g2), l.addStretch(10)

    w.g1.l = l = QFormLayout(w.g1)
    l.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for key, text in (
            ('all', _("A&ll these words:")),
            ('phrase', _("&This exact phrase:")),
            ('any', _("O&ne or more of these words:")),
    ):
        le = QLineEdit(w)
        le.setClearButtonEnabled(True)
        setattr(self, key, le)
        l.addRow(text, le)

    w.g2.l = l = QFormLayout(w.g2)
    l.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    self.none = le = QLineEdit(w)
    le.setClearButtonEnabled(True)
    l.addRow(_("Any of these &unwanted words:"), le)


def create_simple_tab(self, db):
    self.simple_tab = w = QWidget(self.tab_widget)
    self.tab_widget.addTab(w, _("Titl&e/author/series..."))

    w.l = l = QFormLayout(w)
    l.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    self.title_box = le = QLineEdit(w)
    le.setClearButtonEnabled(True)
    le.setObjectName('title_box')
    le.setPlaceholderText(_('The title to search for'))
    l.addRow(_('&Title:'), le)

    self.authors_box = le = EditWithComplete(self)
    le.lineEdit().setPlaceholderText(_('The author to search for'))
    le.setObjectName('authors_box')
    le.setEditText('')
    le.set_separator('&')
    le.set_space_before_sep(True)
    le.set_add_separator(tweaks['authors_completer_append_separator'])
    le.update_items_cache(db.new_api.all_field_names('authors'))
    l.addRow(_('&Author:'), le)

    self.series_box = le = EditWithComplete(self)
    le.lineEdit().setPlaceholderText(_('The series to search for'))
    le.setObjectName('series_box')
    le.set_separator(None)
    le.update_items_cache(db.new_api.all_field_names('series'))
    le.show_initial_value('')
    l.addRow(_('&Series:'), le)

    self.tags_box = le = EditWithComplete(self)
    le.setObjectName('tags_box')
    le.lineEdit().setPlaceholderText(_('The tags to search for'))
    self.tags_box.update_items_cache(db.new_api.all_field_names('tags'))
    l.addRow(_('Ta&gs:'), le)

    searchables = sorted(db.field_metadata.searchable_fields(),
                            key=lambda x: sort_key(x if x[0] != '#' else x[1:]))
    self.general_combo = QComboBox(w)
    self.general_combo.addItems(searchables)
    self.box_last_values = copy.deepcopy(box_values)
    self.general_box = le = QLineEdit(self)
    le.setClearButtonEnabled(True)
    le.setObjectName('general_box')
    l.addRow(self.general_combo, le)
    if self.box_last_values:
        for k,v in self.box_last_values.items():
            if k == 'general_index':
                continue
            getattr(self, k).setText(v)
        self.general_combo.setCurrentIndex(
                self.general_combo.findText(self.box_last_values['general_index']))


def create_date_tab(self, db):
    self.date_tab = w = QWidget(self.tab_widget)
    self.tab_widget.addTab(w, _("&Date search"))
    w.l = l = QVBoxLayout(w)

    def a(w):
        h.addWidget(w)
        return w

    def add(text, w):
        w.la = la = QLabel(text)
        h.addWidget(la), h.addWidget(w)
        la.setBuddy(w)
        return w

    w.h1 = h = QHBoxLayout()
    l.addLayout(h)
    self.date_field = df = add(_("&Search the"), QComboBox(w))
    vals = [((v['search_terms'] or [k])[0], v['name'] or k)
                for k, v in db.field_metadata.iter_items()
                    if v.get('datatype', None) == 'datetime' or
                       (v.get('datatype', None) == 'composite' and
                        v.get('display', {}).get('composite_sort', None) == 'date')]
    for k, v in sorted(vals, key=lambda k_v: sort_key(k_v[1])):
        df.addItem(v, k)
    h.addWidget(df)
    self.dateop_date = dd = add(_("date column for books whose &date is "), QComboBox(w))
    init_dateop(dd)
    w.la3 = la = QLabel('...')
    h.addWidget(la)
    h.addStretch(10)

    w.h2 = h = QHBoxLayout()
    l.addLayout(h)
    self.sel_date = a(QRadioButton(_('&year'), w))
    self.date_year = dy = a(QSpinBox(w))
    dy.setRange(102, 10000)
    dy.setValue(now().year)
    self.date_month = dm = add(_('mo&nth'), QComboBox(w))
    for val, text in [(0, '')] + [(i, strftime('%B', date(2010, i, 1).timetuple())) for i in range(1, 13)]:
        dm.addItem(text, val)
    self.date_day = dd = add(_('&day'), QSpinBox(w))
    dd.setRange(0, 31)
    dd.setSpecialValueText(' \xa0')
    h.addStretch(10)

    w.h3 = h = QHBoxLayout()
    l.addLayout(h)
    self.sel_daysago = a(QRadioButton('', w))
    self.date_daysago = da = a(QSpinBox(w))
    da.setRange(0, 9999999)
    self.date_ago_type = dt = a(QComboBox(w))
    dt.addItems([_('days'), _('weeks'), _('months'), _('years')])
    w.la4 = a(QLabel(' ' + _('ago')))
    h.addStretch(10)

    w.h4 = h = QHBoxLayout()
    l.addLayout(h)
    self.sel_human = a(QRadioButton('', w))
    self.date_human = dh = a(QComboBox(w))
    for val, text in [('today', _('Today')), ('yesterday', _('Yesterday')), ('thismonth', _('This month'))]:
        dh.addItem(text, val)
    connect_lambda(self.date_year.valueChanged, self, lambda self: self.sel_date.setChecked(True))
    connect_lambda(self.date_month.currentIndexChanged, self, lambda self: self.sel_date.setChecked(True))
    connect_lambda(self.date_day.valueChanged, self, lambda self: self.sel_date.setChecked(True))
    connect_lambda(self.date_daysago.valueChanged, self, lambda self: self.sel_daysago.setChecked(True))
    connect_lambda(self.date_human.currentIndexChanged, self, lambda self: self.sel_human.setChecked(True))
    self.sel_date.setChecked(True)
    h.addStretch(10)

    l.addStretch(10)


def create_template_tab(self):
    self.simple_tab = w = QWidget(self.tab_widget)
    self.tab_widget.addTab(w, _("&Template search"))

    w.l = l = QFormLayout(w)
    l.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    self.template_value_box = le = QLineEdit(w)
    le.setClearButtonEnabled(True)
    le.setObjectName('template_value_box')
    le.setPlaceholderText(_('The value to search for'))
    le.setToolTip('<p>' +
                  _("You can use the search test specifications described "
                    "in the calibre documentation. For example, with Number "
                    "comparisons you can the relational operators like '>=' etc. "
                    "With Text comparisons you can use exact, contains "
                    "or regular expression matches. With Date you can use "
                    "today, yesterday, etc. Set/not set takes 'true' for set "
                    "and 'false' for not set.") + '</p>')
    l.addRow(_('Template &value:'), le)

    self.template_test_type_box = le = QComboBox(w)
    le.setObjectName('template_test_type_box')
    for op, desc in [
            ('t', _('Text')),
            ('d', _('Date')),
            ('n', _('Number')),
            ('b', _('Set/Not set'))]:
        le.addItem(desc, op)
    le.setToolTip(_('How the template result will be compared to the value'))
    l.addRow(_('C&omparison type:'), le)

    from calibre.gui2.dialogs.template_line_editor import TemplateLineEditor
    self.template_program_box = le = TemplateLineEditor(self.tab_widget)
    le.setObjectName('template_program_box')
    le.setPlaceholderText(_('The template that generates the value'))
    le.setToolTip(_('Right click to open a template editor'))
    l.addRow(_('Tem&plate:'), le)


def setup_ui(self, db):
    self.setWindowTitle(_("Advanced search"))
    self.setWindowIcon(QIcon(I('search.png')))
    self.l = l = QVBoxLayout(self)
    self.h = h = QHBoxLayout()
    self.v = v = QVBoxLayout()
    l.addLayout(h)
    h.addLayout(v)
    h.addWidget(create_msg_label(self))
    l.addWidget(create_button_box(self))
    v.addLayout(create_match_kind(self))
    self.tab_widget = tw = QTabWidget(self)
    v.addWidget(tw)
    create_adv_tab(self)
    create_simple_tab(self, db)
    create_date_tab(self, db)
    create_template_tab(self)
# }}}


class SearchDialog(QDialog):

    mc = ''

    def __init__(self, parent, db):
        QDialog.__init__(self, parent)
        setup_ui(self, db)

        current_tab = gprefs.get('advanced search dialog current tab', 0)
        self.tab_widget.setCurrentIndex(current_tab)
        if current_tab == 1:
            self.matchkind.setCurrentIndex(last_matchkind)
            focused_field = gprefs.get('advanced_search_simple_tab_focused_field', 'title_box')
            w = getattr(self, focused_field, None)
            if w is not None:
                w.setFocus(Qt.FocusReason.OtherFocusReason)
        elif current_tab == 3:
            self.template_program_box.setText(
                      gprefs.get('advanced_search_template_tab_program_field', ''))
            self.template_value_box.setText(
                      gprefs.get('advanced_search_template_tab_value_field', ''))
            self.template_test_type_box.setCurrentIndex(
                      int(gprefs.get('advanced_search_template_tab_test_field', '0')))
        self.resize(self.sizeHint())

    def save_state(self):
        gprefs['advanced search dialog current tab'] = \
            self.tab_widget.currentIndex()
        if self.tab_widget.currentIndex() == 1:
            fw = self.tab_widget.focusWidget()
            if fw:
                gprefs.set('advanced_search_simple_tab_focused_field', fw.objectName())
        elif self.tab_widget.currentIndex() == 3:
            gprefs.set('advanced_search_template_tab_program_field',
                       unicode_type(self.template_program_box.text()))
            gprefs.set('advanced_search_template_tab_value_field',
                       unicode_type(self.template_value_box.text()))
            gprefs.set('advanced_search_template_tab_test_field',
                       unicode_type(self.template_test_type_box.currentIndex()))

    def accept(self):
        self.save_state()
        return QDialog.accept(self)

    def reject(self):
        self.save_state()
        return QDialog.reject(self)

    def clear_button_pushed(self):
        w = self.tab_widget.currentWidget()
        for c in w.findChildren(QComboBox):
            c.setCurrentIndex(0)
        if w is self.date_tab:
            for c in w.findChildren(QSpinBox):
                c.setValue(c.minimum())
            self.sel_date.setChecked(True)
            self.date_year.setValue(now().year)
        else:
            for c in w.findChildren(QLineEdit):
                c.setText('')
            for c in w.findChildren(EditWithComplete):
                c.setText('')

    def tokens(self, raw):
        phrases = re.findall(r'\s*".*?"\s*', raw)
        for f in phrases:
            raw = raw.replace(f, ' ')
        phrases = [t.strip('" ') for t in phrases]
        return ['"' + self.mc + t + '"' for t in phrases + [r.strip() for r in raw.split()]]

    def search_string(self):
        i = self.tab_widget.currentIndex()
        return (self.adv_search_string, self.box_search_string,
                self.date_search_string, self.template_search_string)[i]()

    def template_search_string(self):
        template = unicode_type(self.template_program_box.text())
        value = unicode_type(self.template_value_box.text()).replace('"', '\\"')
        if template and value:
            cb = self.template_test_type_box
            op =  unicode_type(cb.itemData(cb.currentIndex()))
            l = '{}#@#:{}:{}'.format(template, op, value)
            return 'template:"' + l + '"'
        return ''

    def date_search_string(self):
        field = unicode_type(self.date_field.itemData(self.date_field.currentIndex()) or '')
        op = current_dateop(self.dateop_date)
        prefix = '{}:{}'.format(field, op)
        if self.sel_date.isChecked():
            ans = '{}{}'.format(prefix, self.date_year.value())
            m = self.date_month.itemData(self.date_month.currentIndex())
            if m > 0:
                ans += '-%s' % m
                d = self.date_day.value()
                if d > 0:
                    ans += '-%s' % d
            return ans
        if self.sel_daysago.isChecked():
            val = self.date_daysago.value()
            val *= {0:1, 1:7, 2:30, 3:365}[self.date_ago_type.currentIndex()]
            return '{}{}daysago'.format(prefix, val)
        return '{}{}'.format(prefix, unicode_type(self.date_human.itemData(self.date_human.currentIndex()) or ''))

    def adv_search_string(self):
        mk = self.matchkind.currentIndex()
        if mk == CONTAINS_MATCH:
            self.mc = ''
        elif mk == EQUALS_MATCH:
            self.mc = '='
        else:
            self.mc = '~'
        all, any, phrase, none = map(lambda x: unicode_type(x.text()),
                (self.all, self.any, self.phrase, self.none))
        all, any, none = map(self.tokens, (all, any, none))
        phrase = phrase.strip()
        all = ' and '.join(all)
        any = ' or '.join(any)
        none = ' and not '.join(none)
        ans = ''
        if phrase:
            ans += '"%s"'%phrase
        if all:
            ans += (' and ' if ans else '') + all
        if none:
            ans += (' and not ' if ans else 'not ') + none
        if any:
            if ans:
                ans += ' and (' + any + ')'
            else:
                ans = any
        return ans

    def token(self):
        txt = unicode_type(self.text.text()).strip()
        if txt:
            if self.negate.isChecked():
                txt = '!'+txt
            tok = self.FIELDS[unicode_type(self.field.currentText())]+txt
            if re.search(r'\s', tok):
                tok = '"%s"'%tok
            return tok

    def box_search_string(self):
        mk = self.matchkind.currentIndex()
        if mk == CONTAINS_MATCH:
            self.mc = ''
        elif mk == EQUALS_MATCH:
            self.mc = '='
        else:
            self.mc = '~'

        ans = []
        self.box_last_values = {}
        title = unicode_type(self.title_box.text()).strip()
        self.box_last_values['title_box'] = title
        if title:
            ans.append('title:"' + self.mc + title + '"')
        author = unicode_type(self.authors_box.text()).strip()
        self.box_last_values['authors_box'] = author
        if author:
            ans.append('author:"' + self.mc + author + '"')
        series = unicode_type(self.series_box.text()).strip()
        self.box_last_values['series_box'] = series
        if series:
            ans.append('series:"' + self.mc + series + '"')

        tags = unicode_type(self.tags_box.text())
        self.box_last_values['tags_box'] = tags
        tags = [t.strip() for t in tags.split(',') if t.strip()]
        if tags:
            tags = ['tags:"' + self.mc + t + '"' for t in tags]
            ans.append('(' + ' or '.join(tags) + ')')
        general = unicode_type(self.general_box.text())
        self.box_last_values['general_box'] = general
        general_index = unicode_type(self.general_combo.currentText())
        self.box_last_values['general_index'] = general_index
        global box_values
        global last_matchkind
        box_values = copy.deepcopy(self.box_last_values)
        last_matchkind = mk
        if general:
            ans.append(unicode_type(self.general_combo.currentText()) + ':"' +
                    self.mc + general + '"')
        if ans:
            return ' and '.join(ans)
        return ''


if __name__ == '__main__':
    from calibre.library import db
    db = db()
    from calibre.gui2 import Application
    app = Application([])
    d = SearchDialog(None, db)
    d.exec_()

    print(d.search_string())
