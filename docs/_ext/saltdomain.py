"""
Copied/distilled from Salt doc/_ext/saltdomain.py in order to be able
to use Salt's custom doc refs.
"""


def setup(app):
    app.add_crossref_type(
        directivename="conf_master",
        rolename="conf_master",
        indextemplate="pair: %s; conf/master",
    )
    app.add_crossref_type(
        directivename="conf_minion",
        rolename="conf_minion",
        indextemplate="pair: %s; conf/minion",
    )
    return {"parallel_read_safe": True, "parallel_write_safe": True}
