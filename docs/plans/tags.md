# Plan: tags on to-dos

Status: **done** on `feature/tags` (built on `feature/lists`; not merged yet). Approved by the
owner: 5 tags of at most 30 characters; the filter works within the current list; an unknown
`?tag=` shows "No to-dos tagged …". See "What happened" at the end.

This is feature 14, in wave 5 of [the rollout plan](feature-rollout.md). The merge order in wave 5
is: 13 lists → **14 tags** → 16 drag to reorder. Lists merges **before** this feature; drag merges
after it.

**Where this starts.** The work starts on `main` after waves 1 to 4 (with accounts, 17) and after
**lists (13)** is merged. From [the accounts plan](accounts.md) and [the lists plan](lists.md), this
feature uses:

- `LoginRequiredMiddleware`: every page needs log-in.
- `TodoList` (owner, name). Every `Todo` has a required `list`. `Todo.objects.for_user(user)` goes
  through `TodoList.objects.for_user(user)`. `get_list(request, list_id)` gives one of the person's
  lists, or 404.
- **`Todo.owner` always equals `todo.list.owner`.** `Todo.save()` makes it so (CONVENTIONS,
  "OWNERSHIP"). So the owner of a to-do is the owner of its list, also when an editor makes it on a
  shared list (20).
- The list page is `/lists/<id>/`. `page_context(request, form, current_list)`,
  `back_to_list(request, current_list)`, `list_url(request, current_list)` and
  `filter_links(params, current_list)` all get the list. `list_params(data)` and `list_query(params)`
  do not get it.
- `todo_add(request, list_id)` saves with `form.save(commit=False)`, sets `owner` and `list`, then
  `todo.save()`.
- `TodoEditForm(..., user=request.user)` has a `list` field, so a to-do can move to another list.
- In the tests: `make_user(...)`, `force_login`, and `make_todo(list, title, **fields)`.

## What we want

A **tag** is a short word, like `home` or `urgent`, that a person puts on a to-do. One to-do can
have several tags. The same tag can be on to-dos in **different lists** of the same person.

- In the add form there is one more box: **Tags**, with the hint "separated by commas". A person
  types `home, urgent` and presses Add.
- On each row, the tags are shown as **small links**: `home` `urgent`.
- Clicking a tag shows only the to-dos **in this list** with that tag:
  `/lists/7/?tag=home` (plus the other list settings).
- A **Show all tags** link removes the tag choice again.
- The edit page shows the tags in the same box, as `home, urgent`. Saving replaces them.
- A person only ever sees and uses the tags of **the list's owner**. Today that is always
  themselves.
- No JavaScript.

## Decisions

### Two new things in the database: a `Tag` table, and a link table

```python
class Tag(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=30)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_tag_name_per_owner"),
        ]
```

and on `Todo`, after the other fields:

```python
tags = models.ManyToManyField(Tag, blank=True, related_name="todos")
```

- A **foreign key** is a column that points to one row in another table. `owner` points to a user.
- A **many-to-many** field means "one to-do has many tags, and one tag is on many to-dos". Django
  makes a small third table for it by itself.
- A **unique constraint** is a rule the database keeps: two rows cannot have the same values. Here:
  one person cannot have two tags with the same name. Two people can both have `home`; those are
  **two different rows**.
- `on_delete=models.CASCADE`: when a user is deleted, their tags are deleted too.

### Tag names are cleaned in Python, then saved

`Home`, `HOME` and `home` must be the **same** tag. So the name is cleaned **before** it is saved,
and the database only checks "the same text". We do **not** use a database rule with `Lower("name")`:
SQLite's `LOWER()` only knows A to Z (the search plan found this), so it would not agree with Python
for `CAFÉ` and `café`.

One function, `clean_tag_name(text)`, in `todos/models.py`:

```python
def clean_tag_name(text):
    """A tag name: normal letters, no invisible characters, one space between words, small letters."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(
        " " if unicodedata.category(ch) == "Cc" else ch
        for ch in text
        if unicodedata.category(ch) != "Cf"
    )
    return " ".join(text.split()).lower()
```

1. **NFKC** (`unicodedata.normalize("NFKC", ...)`, part of Python) turns special forms into normal
   letters. For example wide letters: `ｈｏｍｅ` becomes `home`.
2. **Control characters** (category `Cc`: invisible characters like a line break, a tab or `\0`)
   become a space.
3. **Format characters** (category `Cf`: invisible characters like the "zero-width space" or the
   "soft hyphen") are **removed**. Otherwise `home` and `home` + an invisible character would be two
   tags that look the same. One cost: some emoji are made of several emoji joined by an invisible
   "joiner" (`👨‍👩‍👧`). Without the joiner they show as three emoji. We accept this.
4. **Spaces**: `" ".join(text.split())` removes spaces at the ends, and makes many spaces inside
   into one. (`split()` with no argument splits at every kind of space, also the Japanese wide
   space.)
5. **Small letters**: `.lower()`.

If the result is empty, it is not a tag. Cleaning twice gives the same result as cleaning once. The
reviewer checked this for every Unicode character. A unit test checks it for the rows below.

A tag can have a space inside (`go shopping`). It cannot have a comma (see the next part). A `#` is
**kept**: `#home` is a tag named `#home`, not `home`. Removing it brings special cases (`# home`,
`##home`) and is not needed.

### The input: one text box, "separated by commas"

The other way is a **multi-select** (a list box where you pick several existing tags). It is worse
here: a person cannot make a **new** tag with it, and it is hard to use on a phone. So:

- `TodoForm` gets one more field, `tag_names`. It is a normal text box, **not** a model field. Its
  label is **Tags**, with `placeholder="home, urgent"` and the help text "separated by commas".
- The name is `tag_names`, not `tags`: `tags` is the model field, and one name for two different
  things would confuse a reader.
- `clean_tag_names()` in the form turns the text into a list of names:
  1. **NFKC on the whole box first.** This turns the wide comma `，` and the small comma `﹐` into a
     normal `,`. (Doing it on each piece after splitting would be too late: the piece would then
     contain a `,`.)
  2. **Split** at `,` and at the Japanese comma `、` (NFKC does not change `、`).
  3. `clean_tag_name` on each piece.
  4. **Drop** the empty ones (`home,,urgent,` is fine).
  5. **Drop repeats**, keeping the first order (`home, Home, HOME` is one tag).
  6. **Check the length**: a name longer than 30 characters gives the error
     `A tag can be at most 30 characters.` We **refuse**, not cut: this is saved data, and a cut word
     would surprise the person. (Search cuts, because a search is not saved.)
  7. **Check the count**: more than **5** tags gives the error `At most 5 tags on one to-do.`
- The raw box has `max_length=200`, so a huge post is refused early.
- With an error, the page shows the error and **keeps what the person typed**, like every other
  field.

### Tags belong to the list's owner, and are made in one place

`Todo.set_tags(names)`, a method on the model:

```python
def set_tags(self, names):
    """Put exactly these tags on this to-do. Missing tags are made for the list's owner."""
    owner = self.list.owner
    names = dict.fromkeys(n for n in map(clean_tag_name, names) if n)
    tags = [Tag.objects.get_or_create(owner=owner, name=name)[0] for name in names]
    self.tags.set(tags)
```

- The owner comes from **the to-do's list**. It never comes from the form, the address or
  `request.user`. So when Ana posts `secret` while Ben has a tag `secret`, Ana gets **her own new**
  `secret` tag. Ben's row is never touched. A test checks this.
- `self.list.owner` and `self.owner` are the same (CONVENTIONS). We write `list.owner` because it
  says **why**: tags follow the list.
- `set_tags` cleans the names itself (`clean_tag_name`, then drop empty ones and repeats). So every
  way to set tags gives clean names, not only the form.
- `get_or_create` finds the tag, or makes it. If two requests make the same tag at the same moment,
  the unique constraint stops the second one, and Django then finds the row the first one made.
- `self.tags.set(tags)` makes the to-do have **exactly** these tags: it adds the new ones and
  removes the others.
- At most 5 names, so at most a few small queries. That is fine.

### The form saves the tags, also with `commit=False`

Lists' `todo_add` saves with `form.save(commit=False)`, then `todo.save()`. With `commit=False`,
Django does **not** save many-to-many data at once. It gives the form a method `save_m2m()` to call
later. (`m2m` means many-to-many.) So we put the tag saving where Django saves many-to-many data,
`_save_m2m()`:

```python
def _save_m2m(self):
    super()._save_m2m()
    self.instance.set_tags(self.cleaned_data["tag_names"])
```

- With `form.save()` (the edit view): Django calls `_save_m2m()` by itself, after the to-do is saved.
- With `form.save(commit=False)` (the add view): `form.save_m2m()` calls `_save_m2m()`. So
  `todo_add` gets **one more line**, after `todo.save()`:

  ```python
  form.save_m2m()
  ```

  This is the normal Django pattern for `commit=False`. Without it, the tags are silently lost.
  A test adds a to-do through `/lists/<id>/add/` and checks the tags are saved.
- `_save_m2m` starts with `_`: it is not in Django's public documentation. The reviewer checked it
  works in our Django version (5.2). A test catches it if a new Django changes it.

On the edit page, the box starts with the saved tags, in a-b-c order. In `TodoForm.__init__`:

```python
if self.instance.pk:
    self.initial["tag_names"] = ", ".join(tag.name for tag in self.instance.tags.all())
```

`TodoEditForm` gets all of this from `TodoForm`.

### Tags are set only through the form

There is **no** separate address to set tags, and **no** `/tags/` page (CONVENTIONS). Every tag
change goes through `TodoForm` or `TodoEditForm`, and so through `set_tags`. And the admin cannot
attach tags (see "The admin"). **This is what keeps another person's tag off a to-do**: there is
only one way in, and it always uses the list's owner.

**For sharing (20).** An editor on Ana's shared list may tag. The tags they make or use are
**Ana's** tags, because `set_tags` uses the list's owner. This needs no extra code.

### Moving a to-do to another list

The edit page can move a to-do to another list (from 13). The edit form saves the list first, then
`_save_m2m` runs `set_tags` with the names in the box, for the **new** list's owner. So the names
stay, and the rows are the new owner's. Today the old and the new owner are the same person.

**Note for sharing (20)**, also in `AGENTS.md`: if a to-do is ever moved to a list with a
**different** owner **without** `TodoEditForm`, the code must call `todo.tags.clear()`. Otherwise
the to-do keeps the old owner's tags.

### Tags that are no longer used: we leave them

When the last to-do drops a tag, the `Tag` row stays. **This is the simplest choice**:

- The page never shows a list of all tags, so an unused tag is not seen anywhere (only in the admin).
- If the person uses `home` again, the same row is found again.
- Deleting would need code in toggle, delete, delete completed, edit, and list delete. Each place is
  a chance for a bug.

A test checks this choice, so a later change to it is made on purpose.

### Tags on each row: small links

```html
{% if todo.tags.all %}
  <ul class="tags" aria-label="Tags">
    {% for tag in todo.tags.all %}
      <li><a class="tag" href="{{ tag_link_prefix }}{{ tag.name|urlencode:'' }}"{% if tag.name == current_tag %} aria-current="true"{% endif %}>{{ tag.name }}</a></li>
    {% endfor %}
  </ul>
{% endif %}
```

- `current_tag` is the chosen tag name from the view, or `""`.
- `tag_link_prefix` comes from the view: the list address, the other list settings, and then
  `tag=`. For example `/lists/7/?show=active&tag=` or `/lists/7/?tag=`.
- `urlencode:''` makes **every** special character safe in an address: `&`, `=`, `/`, a space
  (`%20`), Japanese letters. So a tag named `a&show=x` cannot add a setting. A test checks this, and
  a test follows the link of `go shopping` and gets the right list.
- The name is **autoescaped**: Django turns `<` into `&lt;` and so on, so a tag named `<b>` is shown
  as text.

### One query for all tags on the page

Without care, the page makes one query for the list, then **one more query per row** to get its
tags. With 50 to-dos, that is 51 queries. So `page_context` adds:

```python
todos = todos.prefetch_related("tags")
```

`prefetch_related` gets the tags of **every** to-do on the page in **one** extra query. The template's
`todo.tags.all` then reads from memory. Because `Tag.Meta.ordering = ["name"]`, the tags come in
a-b-c order. A test checks that the number of queries is the **same** for 1 to-do with 1 tag and for
5 to-dos with 3 tags each.

### The tag filter: `?tag=home`

- **`list_params` checks the shape** of `tag`: it runs `clean_tag_name`, and keeps it only if it is
  not empty and is at most 30 characters. So `?tag=HOME` becomes `?tag=home`. No database here, like
  the `show` and `q` checks, so `back_to_list` stays safe.
- **A new step reads the database**, after the other steps:

  ```python
  def tag_todos(todos, params):
      """Only the to-dos with the chosen tag (a tag of the to-do's list owner)."""
      tag = params.get("tag")
      if tag:
          return todos.filter(tags__name=tag, tags__owner=F("list__owner"))
      return todos
  ```

  `todos` already has only the to-dos of this list. `F("list__owner")` reads the list's owner from
  the same row. So the filter says what CONVENTIONS says: "the list owner's tag with this name". On a
  shared list (20), it will read the list owner's tags with no change.

**A tag name with no to-dos** (`?tag=banana`): the list is empty, and the page says
`No to-dos tagged "banana".` We do **not** quietly drop it and show everything: the address says
`banana`, so the page should too. It is safe: the page is **exactly the same** whether or not
another person has a tag `banana`. A test checks this, so nobody can learn other people's tag names
by trying them.

### Within the current list, not across all lists

**Decision: the tag filter shows matches in the current list only.**

- The page shows one list. `show`, `q` and `sort` all work inside the current list. A tag is one
  more setting of the same kind, so it works the same way. One rule, no surprise.
- A page "every to-do tagged `home`, from every list" is a **new page**: which list is each row in,
  where does Add go, what does the count mean? That is a bigger design. It is in "What we will not
  do (yet)".
- The tags **themselves** cross lists: the same `home` row is used in every list of that person.

### The current tag on the page

When a tag is chosen, above the list:

```html
<p class="current-tag">Tagged <strong>{{ current_tag }}</strong> · <a href="{{ clear_tag_url }}">Show all tags</a></p>
```

`clear_tag_url` is the same list address without `tag`, with the other settings. The filter links,
the sort links, the search form's hidden inputs, every `POST` form and every redirect keep `tag`
**by themselves**, because it is in `list_params` (as for `q` in the search plan).

### The empty message

| What is chosen | Message |
|---|---|
| a search (and maybe a tag) | `No to-dos match "milk".` (as today) |
| a tag, no search | `No to-dos tagged "home".` |
| neither | the messages from today |

### The admin

- `TagAdmin`: `list_display = ["name", "owner"]`, `list_filter = ["owner"]`,
  `search_fields = ["name"]`. **Read-only**: `has_add_permission` returns `False`, and `owner` and
  `name` are in `readonly_fields`. So the admin cannot make `HOME` next to `home`, or move a tag to
  another person. Deleting a tag in the admin is allowed (it only takes it off the to-dos).
- In the `Todo` admin, `tags` is in `readonly_fields`. The admin's normal box would offer **every
  person's** tags, and could attach another person's tag.

## What we will not do (yet)

- **No page "all to-dos with this tag, across lists".** See the decision above.
- **No deleting of unused tags**, and no page to rename or delete a tag. Only the admin can delete.
- **No list of all my tags**, and no choosing of tags from a list. Only the text box.
- **No picking more than one tag at a time** (`home` AND `urgent`).
- **No colours for tags.**
- **No `casefold()`.** `casefold` would make `Straße` and `STRASSE` the same tag. `.lower()` does not.
  This is rare; we keep `.lower()`, which is easier to explain.
- **No removing a `#` at the start.** `#home` and `home` are two tags.
- **No matching of katakana with hiragana** (`カイモノ` and `かいもの` are two tags), as in search.
- **No search in tag names** from the search box.
- **No JavaScript** (no suggestions while typing).

## Changes in behaviour

1. The add form and the edit page have a **Tags** box.
2. Saving a to-do with `home, Urgent` gives it the tags `home` and `urgent`. Missing tags are made
   for the list's owner.
3. Each row shows its tags as links, in a-b-c order.
4. `/lists/<id>/?tag=home` shows only the to-dos in this list with the tag `home`, a line "Tagged
   **home** · Show all tags", and, if none, `No to-dos tagged "home".`
5. The filter links, the sort links, the search form, every `POST` form and every redirect keep
   `tag`.
6. Too long a tag, or more than 5, gives an error and keeps what the person typed.

What stays the same:

- A to-do with no tags looks as before (no empty `<ul>`).
- The count and "Delete completed" still use the whole list, not what the tag shows (as for filter
  and search).
- Every change is still `POST` only. A tag link is a `GET` that only reads.
- Nobody sees, matches or changes another person's tag.

## The changes, one file at a time

### 1. `todos/models.py`

- `import unicodedata` and `from django.db.models import F` where needed.
- `TAG_MAX_LENGTH = 30`, `TAGS_PER_TODO = 5`, and `clean_tag_name(text)`, near the top.
- The `Tag` model (see Decisions), with `__str__` returning the name. It goes **above** `Todo`,
  because `Todo` points at it. **No** `save()` of its own: `set_tags` cleans names, and the admin
  cannot add tags.
- On `Todo`: the `tags` field, and `set_tags(names)`.

### 2. `todos/migrations/` — made by Django

`uv run python manage.py makemigrations`. It makes the `Tag` table, its constraint, and the link
table. **No data migration**: old to-dos simply have no tags. The merge queue makes this file again
after lists (13) is merged.

### 3. `todos/forms.py`

In `TodoForm`:

```python
tag_names = forms.CharField(
    label="Tags",
    required=False,
    max_length=200,
    help_text="separated by commas",
    widget=forms.TextInput(attrs={"placeholder": "home, urgent"}),
)
```

- It is **not** in `Meta.fields`, so Django does not try to save it by itself.
- `clean_tag_names()`, the start value in `__init__`, and `_save_m2m()` as in Decisions.
- `TodoEditForm` needs no change: it gets all of this from `TodoForm`.

### 4. `todos/views.py`

- In `list_params`, after the other checks:

  ```python
  tag = clean_tag_name(data.get("tag") or "")
  if tag and len(tag) <= TAG_MAX_LENGTH:
      params["tag"] = tag
  ```

- `tag_todos(todos, params)` (see Decisions). In `page_context`, one line after the other steps, and
  one line for the prefetch:

  ```python
  todos = tag_todos(todos, params)        # new
  todos = todos.prefetch_related("tags")  # new
  ```

- Three new keys in `page_context`, one per line. `without_tag` is `params` without `"tag"`, and
  `here = reverse("todo_list", args=[current_list.pk])`:

  ```python
  "current_tag": params.get("tag", ""),
  "tag_link_prefix": here + list_query({**without_tag, "tag": ""}),
  "clear_tag_url": here + list_query(without_tag),
  ```

  `list_query({..., "tag": ""})` ends with `tag=`, so the template only adds the encoded name.
  We do not use `list_url(request, current_list)` here: it reads the address of the request, and we
  need it **without** `tag`.
- `todo_add`: one new line, `form.save_m2m()`, right after `todo.save()`.
- **No other view changes.** `todo_edit` uses `form.save()`, which saves the tags.

### 5. `todos/templates/todos/todo_list.html`

- The **Tags** box in the add form, after the other fields: its errors, its label, the box and the
  help text.
- The tag links on each row (see Decisions), after the title.
- The "Tagged … · Show all tags" line above the list, only when a tag is chosen.
- The empty message gets the tag case, after the search case.
- CSS (in `base.html` if the shared CSS lives there):

  ```css
  ul.tags { display: inline-flex; flex-wrap: wrap; gap: 0.25rem; margin: 0; padding: 0; }
  ul.tags li { padding: 0; border: 0; }
  a.tag { font-size: 0.8rem; padding: 0 0.4rem; border: 1px solid #999; border-radius: 0.6rem; text-decoration: none; }
  a.tag[aria-current] { font-weight: bold; }
  ```

  `ul.tags li` takes away the normal row style (`li` has a border and padding for to-do rows).

### 6. `todos/templates/todos/todo_edit.html`

If it draws the fields in a loop, no change. If not, add the Tags box like on the add form.

### 7. `todos/admin.py`

`TagAdmin` (read-only, see Decisions), and `tags` in the `Todo` admin's `readonly_fields`.

### 8. `AGENTS.md`

- `todos/models.py` row: "`Tag` (owner, name). A tag name is cleaned and in small letters
  (`clean_tag_name`); one name per person. `Todo.tags`. `Todo.set_tags(names)` makes missing tags
  for the **list's owner**."
- `todos/forms.py` row: "The Tags box: names separated by commas, at most 5, each at most 30
  characters. Tags are saved in `_save_m2m`, so a view with `save(commit=False)` must call
  `form.save_m2m()`."
- `todos/views.py` row: "`?tag=home` shows the to-dos in this list with that tag."
- Rules: "Tags are set only through `TodoForm`/`TodoEditForm`. Code that moves a to-do to a list with
  a different owner without that form must call `todo.tags.clear()`."

## Tests (`todos/tests/`)

We write all of these **first**, and run them **before** changing the code. Two people: **ana**
(logged in with `force_login`) and **ben**, each with their list "My to-dos". Ana also has "Work".
Elements are checked exactly with `assertContains(..., html=True)`; redirects with
`response["Location"]`, exactly. To-dos are made with `make_todo(list, title, ...)`.

### Bottom: unit tests (`todos/tests/unit/test_tags.py`, new file)

**One table** for `clean_tag_name`, `test_clean_tag_name`, one `subTest` per row. Each row also
checks that cleaning twice gives the same result.

| In | Out | Why |
|---|---|---|
| `" Home "` | `"home"` | spaces at the ends, small letters |
| `"ｈｏｍｅ"` | `"home"` | wide letters (NFKC) |
| `"go   shopping"` | `"go shopping"` | many spaces become one |
| `"a　b"` | `"a b"` | the Japanese wide space |
| `"a\x00b"`, `"a\tb"` | `"a b"` | control characters become a space |
| `"home​"`, `"­home"` | `"home"` | invisible format characters are removed |
| `"#home"` | `"#home"` | a `#` is kept |
| `"# home"` | `"# home"` | a `#` is kept |
| `"##home"` | `"##home"` | a `#` is kept |
| `"CAFÉ"` | `"café"` | small letters, not only A to Z |
| `"牛乳"` | `"牛乳"` | Japanese is unchanged |
| `""`, `"   "`, `"​"` | `""` | nothing left |

How it fails today: `ImportError` (no `clean_tag_name`).

| Test | What it checks | How it fails today |
|---|---|---|
| `test_form_parses_tags` | `subTest` rows of `tag_names` → `cleaned_data["tag_names"]`: `"home, Urgent,,HOME, "` → `["home", "urgent"]`; `"牛乳、買い物"` → `["牛乳", "買い物"]`; `"a，b"` → `["a", "b"]`; `"a﹐b"` → `["a", "b"]`; `""` → `[]` | `KeyError`: no field |
| `test_form_refuses_a_long_tag` | 31 × `a` → error `A tag can be at most 30 characters.`; 30 × `a` → valid | the form is valid |
| `test_form_refuses_too_many_tags` | `a,b,c,d,e,f` → error `At most 5 tags on one to-do.`; `a,b,c,d,e` → valid; `a,a,a,a,a,a,b` → valid (repeats are dropped **before** counting) | the form is valid |
| `test_form_with_errors_keeps_the_input` | a bound form with `a,b,c,d,e,f`: the rendered box has `value="a,b,c,d,e,f"` (exact element) | no box |
| `test_edit_form_shows_saved_tags` | a to-do with tags `urgent` and `home`; `TodoEditForm(instance=todo, user=ana)`: the box starts with `"home, urgent"` (a-b-c order) | no field |
| `test_list_params_keeps_a_tag` | `tag=Home` → `{"tag": "home"}`; `tag=go%20shopping` → `{"tag": "go shopping"}`; `tag=` and `tag=%20` → `{}`; 31 × `a` → `{}` | `{}`: `tag` is dropped |
| `test_set_tags_uses_the_list_owner` | `todo.set_tags(["Home", "home", ""])` on a to-do in ana's list: exactly one tag `home`, `owner=ana` | no `set_tags` |
| `test_tag_names_are_unique_per_person` | `Tag.objects.create(owner=ana, name="home")`, then the same again **inside `transaction.atomic()`** in `assertRaises(IntegrityError)`; then ben can make `home` | no `Tag` model |

`transaction.atomic()` around the second create: after an `IntegrityError`, the test's database
transaction is broken. Wrapping only that line keeps the rest of the test working.

The model tests use the database, so they use `TestCase`, like lists' unit tests.

### Middle: integration tests (`todos/tests/integration/test_tags.py`, new file)

A new file, so it does not clash with drag (16).

| Test | What it does | What it checks | How it fails today |
|---|---|---|---|
| `test_add_saves_tags` | ana posts to `/lists/<id>/add/` `Buy milk` with tags `home, urgent` | the to-do has tags `home`, `urgent`; both rows have `owner=ana` | no tags (this test fails if `form.save_m2m()` is missing) |
| `test_add_reuses_an_existing_tag` | ana has `home`; she adds a to-do with `Home` | ana has exactly one tag; the to-do has that row | no tags |
| `test_posting_a_tag_name_never_uses_another_persons_tag` | ben has `Tag(secret)` on one of his to-dos; ana adds a to-do with `secret` | ana's to-do's tag has `owner=ana`, and its `pk` is not ben's; ben's row and ben's to-do are unchanged; there are two `secret` rows | no tags |
| `test_another_persons_tags_never_appear` | ben has a to-do tagged `bobsecret`; ana opens her list | no element `<a class="tag" …>bobsecret</a>` on the page (`html=True`, `count=0`) | **passes today** (protecting). Check it with a bug: drop `for_user` in `page_context` |
| `test_tag_filter_is_the_same_whether_or_not_someone_has_the_tag` | ana opens `/lists/<id>/?tag=secret`, before and after ben makes a to-do tagged `secret` | the two pages are the same (compare the list part), and show `No to-dos tagged "secret".` | no message |
| `test_tag_links_on_each_row` | a to-do with `urgent`, `home` | `<ul class="tags" aria-label="Tags"><li><a class="tag" href="/lists/<id>/?tag=home">home</a></li><li><a class="tag" href="/lists/<id>/?tag=urgent">urgent</a></li></ul>` (a-b-c order) | no links |
| `test_no_tags_no_list` | a to-do with no tags | no `ul class="tags"` in that row | **passes today** (protecting). Check it with a bug: remove the `{% if %}` |
| `test_tag_link_keeps_the_other_settings` | open `/lists/<id>/?show=active&q=milk` | the tag link is `/lists/<id>/?show=active&amp;q=milk&amp;tag=home` | no links |
| `test_tag_link_is_safe` | tags named `a&show=x` and `<b>` | the links end with `tag=a%26show%3Dx` and `tag=%3Cb%3E`; the text is `&lt;b&gt;` | no links |
| `test_tag_link_with_a_space_works` | a to-do tagged `go shopping`; take its link from the page and open it | the link ends with `tag=go%20shopping`; the opened page shows that to-do and "Tagged go shopping" | no links |
| `test_tag_filter_shows_only_tagged_todos` | `Buy milk` (home), `Call mum` (no tag); open `?tag=home` | `Buy milk` is there; `Call mum` is not; the "Tagged home" line with `<a href="/lists/<id>/">Show all tags</a>` | `Call mum` is shown |
| `test_tag_filter_is_within_the_current_list` | ana has a `home` to-do in "My to-dos" and one in "Work"; open "My to-dos" with `?tag=home` | only the "My to-dos" one is shown | both shown (`tag` ignored, but the list already limits); the "Tagged" line is missing |
| `test_tag_filter_works_with_show_and_search` | `?show=active&q=milk&tag=home` | only active, `milk`, `home` to-dos | `tag` ignored |
| `test_every_post_form_keeps_the_tag` | open `?tag=home` | every `POST` form action ends with `?tag=home` (the helper in `helpers.py`) | ends with `""` |
| `test_done_keeps_the_tag` | post Done with `?tag=home` | redirect to `/lists/<id>/?tag=home` | redirect without `tag` |
| `test_bad_tags_keep_the_input` | post to add with `a,b,c,d,e,f` | 200, the error, the box still has `a,b,c,d,e,f`, no to-do saved | the to-do is saved |
| `test_edit_replaces_tags` | to-do with `home`; GET the edit page → box value `home`; POST tags `work` | the to-do has only `work` | no box |
| `test_unused_tag_is_kept` | edit the only `home` to-do to no tags | the `Tag(home)` row still exists | no tags |
| `test_list_page_query_count_does_not_grow` | `assertNumQueries` on the list page with 1 to-do with 1 tag, then with 5 to-dos with 3 tags each | the same number both times | the page does not show tags yet. Check with a bug: remove `prefetch_related` and see it fail |
| `test_admin_tags_are_read_only` | a staff user: the `Tag` list page loads; the "add tag" page gives 403; the `Todo` change page has no box for choosing tags | no `Tag` admin |

### Top: the CUJ test (`todos/tests/cuj/test_journeys.py`)

**One new journey**, `test_tag_a_todo_and_filter_by_it`, because "click a tag to see a group" is a
new way to use the app:

1. Ana logs in, adds `Buy milk` with tags `home, urgent`, and adds `Write report` with tag `work`.
2. The `Buy milk` row has the links `home` and `urgent`.
3. She clicks `home`. Only `Buy milk` is shown, and "Tagged **home**".
4. She presses Done on `Buy milk`. She is still on the `home` tag.
5. She clicks "Show all tags". Both to-dos are shown.

How it fails today: there is no Tags box (`get_by_label("Tags")` finds nothing).

Check the old journeys still pass: `get_by_label("New to-do")` must not also find "Tags".

## Steps, in order

1. **Check the base.** On the newest `main` (with lists), read `models.py`, `views.py`, `forms.py`
   and the test helpers. Check the names in "Where this starts". If one is very different, stop and
   tell the orchestrator.
2. Make a worktree and the branch `feature/tags` from `main`.
3. Write the unit tests. Run them. Show them failing.
4. Write the integration tests and the CUJ test. Run them. Show them failing. For each protecting
   test, show it failing against its deliberate bug, then undo the bug.
5. `models.py`: `clean_tag_name`, `Tag`, `Todo.tags`, `set_tags`. Run `makemigrations` and
   `migrate`.
6. `forms.py`, then `views.py` (with `form.save_m2m()` in `todo_add`), then the templates, then
   `admin.py`.
7. Run the tests until all pass. Run `make check` and `make test-cuj`.
8. Update `AGENTS.md`.
9. Open the PR. It joins the merge queue after lists (13). The merge queue makes the migration again.

## Risks

- **A view with `save(commit=False)` forgets `form.save_m2m()`.** Then tags are lost with no error.
  `test_add_saves_tags` catches it for add; the `AGENTS.md` rule warns later features.
- **`_save_m2m` is not public Django.** It works in Django 5.2 (checked). If a Django upgrade
  changes it, `test_add_saves_tags` and `test_edit_replaces_tags` fail.
- **Another person's tag on a to-do.** Prevented because tags are set only by `set_tags` (always the
  list's owner) and the admin is read-only. Tests check that a posted name never uses another
  person's row, and that other people's tags never show.
- **Sharing (20) moves a to-do without the edit form.** It must clear the tags. Written in
  `AGENTS.md`.
- **Clash with drag (16).** Drag changes the row in the template and the order of the list. The tag
  links are one new block after the title. `prefetch_related` does not change the order.
- **Many unused tags pile up.** Not seen on the page; harmless. Cleanup is for later.

## Open questions for the owner

1. Is **5 tags per to-do, 30 characters per tag** right?
2. The filter is **within the current list**. Do you want an "all lists" tag page later?
3. A tag with no to-dos (`?tag=banana`) shows "No to-dos tagged banana" instead of quietly showing
   the whole list. OK?

## What happened

Built on `feature/lists` (lists, 13, not merged yet), tests first.

**Names.** CONVENTIONS wins over this plan where they differ: the foreign key is `todo_list`, not
`list`. So `set_tags` uses `self.todo_list.owner`, and the filter is
`tags__owner=F("todo_list__owner")`.

**The red run.** The tests were written and committed first. Before the code: the two new test
files could not import (`Tag` and `clean_tag_name` did not exist), the canary test could not set
up (`Todo` had no `set_tags`), and the new journey found no "Tags" label. Every other test passed.

**Differences from the plan, and why.**

- `todo_add` on the lists branch saves with `form.save()`, not `save(commit=False)`. `save()`
  calls `_save_m2m()` by itself, so **no view changed**. `todo_edit` already called
  `form.save_m2m()`. A unit test checks `save(commit=False)` + `save_m2m()` too.
- `Tag.objects.owned_by(user)` is new: the guard test (accounts, 17) now also checks `Tag`, so
  every tag query needs a scoped entry point. `set_tags` uses
  `Tag.objects.owned_by(owner).get_or_create(owner=owner, name=name)`.
- **A tag link drops `selected`** (the pane closes). The plan's `without_tag` kept it, which would
  put `selected` before `tag` in the address; `selected` must stay last.
- **Repeating to-dos copy their tags** to the next copy (like their steps). The plan did not say;
  the repeating guard test asked for a decision. The copy is in the same list, so the tags are
  the same owner's. A unit test checks it.
- The tag links are a small template, `tag_list.html`, used by the row and by the details pane,
  which has a **Tags** row after Priority (the pane's tags come from the same prefetch).
- `?tag=` runs after `sort_todos` (`tag_todos`), then `prefetch_related("tags")`, both before
  `selected_todo`.
- The journey uses the test client (CONVENTIONS: no real-browser tests).
- Two existing tests learned about the new field: the edit form's field list (`tag_names`, not
  `tags`) and the add form's widgets.

**Deliberate bugs, each caught, then put back:** no `_save_m2m` (10 tests, the journey too);
`set_tags` with the person saving instead of the list owner
(`test_tags_belong_to_the_list_owner_not_the_person_saving`); the prefetch after `selected_todo`
(`test_selecting_a_tagged_todo_adds_no_queries` and two pane tests); no prefetch at all (the
query-count tests); the filter without the owner condition
(`test_a_tag_of_the_same_name_from_another_person_does_not_match`); a page with every to-do (the
canary, `test_another_persons_tags_never_appear` and many more); no `{% if %}` around the tag list
(`test_no_tags_no_list` and the journeys); the name not encoded in the link
(`test_tag_link_is_safe`, `test_tag_link_with_a_space_works`); `tag` not kept by `list_params`
(16 tests).

**Migration.** `0013_tag_todo_tags_tag_unique_tag_name_per_owner` (made by Django; the merge queue
makes it again). Checked on a database at 0012 with two to-dos: forward keeps them (no tags),
`set_tags` works, backward to 0012 removes both tag tables and keeps the to-dos, forward again
works.

**By eye** (headless Chrome, 1280 × 800, logged in through the log-in form, own database; then the
server was stopped and the database deleted):

- `tags-list-1280.png`: the Tags box with "home, urgent" and "separated by commas" after Repeats;
  each row's tags as small rounded links between the title and Edit; no empty space on "Pay rent".
- `tags-filter-home-1280.png` / `tags-pane-1280.png`: "Tagged **home** · Show all tags" above the
  list, only the three `home` to-dos, the chosen tag bold with a blue border, and the pane's Tags
  row.
- `tags-filter-none-1280.png`: `No to-dos tagged "banana".`; the count still says "4 items left".
