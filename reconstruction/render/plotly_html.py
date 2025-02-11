"""
Contents of this file are copied from the plotly.py and a feature is added
that enables data compression in the exported html file.
You can find the changes in pull-request: https://github.com/plotly/plotly.py/pull/3117

The contents of this file are licensed:

The MIT License (MIT)

Copyright (c) 2016-2018 Plotly, Inc

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import uuid
import json
import os
import webbrowser

import base64
import gzip

import six

from plotly.io._utils import validate_coerce_fig_to_dict
from plotly.offline.offline import _get_jconfig, get_plotlyjs
from plotly import utils


# Build script to set global PlotlyConfig object. This must execute before
# plotly.js is loaded.
_window_plotly_config = """\
<script type="text/javascript">\
window.PlotlyConfig = {MathJaxConfig: 'local'};\
</script>"""

_mathjax_config = """\
<script type="text/javascript">\
if (window.MathJax) {MathJax.Hub.Config({SVG: {font: "STIX-Web"}});}\
</script>"""


def to_html(
    fig,
    config=None,
    auto_play=True,
    include_plotlyjs=True,
    include_mathjax=False,
    post_script=None,
    full_html=True,
    animation_opts=None,
    default_width="100%",
    default_height="100%",
    validate=True,
    compress=True,
):
    """
    Convert a figure to an HTML string representation.
    Parameters
    ----------
    fig:
        Figure object or dict representing a figure
    config: dict or None (default None)
        Plotly.js figure config options
    auto_play: bool (default=True)
        Whether to automatically start the animation sequence on page load
        if the figure contains frames. Has no effect if the figure does not
        contain frames.
    include_plotlyjs: bool or string (default True)
        Specifies how the plotly.js library is included/loaded in the output
        div string.
        If True, a script tag containing the plotly.js source code (~3MB)
        is included in the output.  HTML files generated with this option are
        fully self-contained and can be used offline.
        If 'cdn', a script tag that references the plotly.js CDN is included
        in the output. HTML files generated with this option are about 3MB
        smaller than those generated with include_plotlyjs=True, but they
        require an active internet connection in order to load the plotly.js
        library.
        If 'directory', a script tag is included that references an external
        plotly.min.js bundle that is assumed to reside in the same
        directory as the HTML file.
        If 'require', Plotly.js is loaded using require.js.  This option
        assumes that require.js is globally available and that it has been
        globally configured to know how to find Plotly.js as 'plotly'.
        This option is not advised when full_html=True as it will result
        in a non-functional html file.
        If a string that ends in '.js', a script tag is included that
        references the specified path. This approach can be used to point
        the resulting HTML file to an alternative CDN or local bundle.
        If False, no script tag referencing plotly.js is included. This is
        useful when the resulting div string will be placed inside an HTML
        document that already loads plotly.js. This option is not advised
        when full_html=True as it will result in a non-functional html file.
    include_mathjax: bool or string (default False)
        Specifies how the MathJax.js library is included in the output html
        div string.  MathJax is required in order to display labels
        with LaTeX typesetting.
        If False, no script tag referencing MathJax.js will be included in the
        output.
        If 'cdn', a script tag that references a MathJax CDN location will be
        included in the output.  HTML div strings generated with this option
        will be able to display LaTeX typesetting as long as internet access
        is available.
        If a string that ends in '.js', a script tag is included that
        references the specified path. This approach can be used to point the
        resulting HTML div string to an alternative CDN.
    post_script: str or list or None (default None)
        JavaScript snippet(s) to be included in the resulting div just after
        plot creation.  The string(s) may include '{plot_id}' placeholders
        that will then be replaced by the `id` of the div element that the
        plotly.js figure is associated with.  One application for this script
        is to install custom plotly.js event handlers.
    full_html: bool (default True)
        If True, produce a string containing a complete HTML document
        starting with an <html> tag.  If False, produce a string containing
        a single <div> element.
    animation_opts: dict or None (default None)
        dict of custom animation parameters to be passed to the function
        Plotly.animate in Plotly.js. See
        https://github.com/plotly/plotly.js/blob/master/src/plots/animation_attributes.js
        for available options. Has no effect if the figure does not contain
        frames, or auto_play is False.
    default_width, default_height: number or str (default '100%')
        The default figure width/height to use if the provided figure does not
        specify its own layout.width/layout.height property.  May be
        specified in pixels as an integer (e.g. 500), or as a css width style
        string (e.g. '500px', '100%').
    validate: bool (default True)
        True if the figure should be validated before being converted to
        JSON, False otherwise.
    compress: bool (default False)
        If True, the figure data is compressed reducing the total file size.
        It adds an external compression library which requires an active 
        internet connection.
    Returns
    -------
    str
        Representation of figure as an HTML div string
    """

    # ## Validate figure ##
    fig_dict = validate_coerce_fig_to_dict(fig, validate)

    # ## Generate div id ##
    plotdivid = str(uuid.uuid4())

    # ## Serialize figure ##
    jdata = json.dumps(
        fig_dict.get("data", []), cls=utils.PlotlyJSONEncoder, sort_keys=True
    )

    jlayout = json.dumps(
        fig_dict.get("layout", {}), cls=utils.PlotlyJSONEncoder, sort_keys=True
    )

    if fig_dict.get("frames", None):
        jframes = json.dumps(fig_dict.get("frames", []), cls=utils.PlotlyJSONEncoder)
    else:
        jframes = None

    # ## Serialize figure config ##
    config = _get_jconfig(config)

    # Set responsive
    config.setdefault("responsive", True)

    # Get div width/height
    layout_dict = fig_dict.get("layout", {})
    template_dict = fig_dict.get("layout", {}).get("template", {}).get("layout", {})

    div_width = layout_dict.get("width", template_dict.get("width", default_width))
    div_height = layout_dict.get("height", template_dict.get("height", default_height))

    # Add 'px' suffix to numeric widths
    try:
        float(div_width)
    except (ValueError, TypeError):
        pass
    else:
        div_width = str(div_width) + "px"

    try:
        float(div_height)
    except (ValueError, TypeError):
        pass
    else:
        div_height = str(div_height) + "px"

    # ## Get platform URL ##
    if config.get("showLink", False) or config.get("showSendToCloud", False):
        # Figure is going to include a Chart Studio link or send-to-cloud button,
        # So we need to configure the PLOTLYENV.BASE_URL property
        base_url_line = """
                    window.PLOTLYENV.BASE_URL='{plotly_platform_url}';\
""".format(
            plotly_platform_url=config.get("plotlyServerURL", "https://plot.ly")
        )
    else:
        # Figure is not going to include a Chart Studio link or send-to-cloud button,
        # In this case we don't want https://plot.ly to show up anywhere in the HTML
        # output
        config.pop("plotlyServerURL", None)
        config.pop("linkText", None)
        config.pop("showLink", None)
        base_url_line = ""

    # ## Build script body ##
    # This is the part that actually calls Plotly.js

    # build post script snippet(s)
    then_post_script = ""
    if post_script:
        if not isinstance(post_script, (list, tuple)):
            post_script = [post_script]
        for ps in post_script:
            then_post_script += """.then(function(){{
                            {post_script}
                        }})""".format(
                post_script=ps.replace("{plot_id}", plotdivid)
            )

    then_addframes = ""
    then_animate = ""
    if jframes:
        then_addframes = """.then(function(){{
                            Plotly.addFrames('{id}', {frames});
                        }})""".format(
            id=plotdivid, frames=jframes
        )

        if auto_play:
            if animation_opts:
                animation_opts_arg = ", " + json.dumps(animation_opts)
            else:
                animation_opts_arg = ""
            then_animate = """.then(function(){{
                            Plotly.animate('{id}', null{animation_opts});
                        }})""".format(
                id=plotdivid, animation_opts=animation_opts_arg
            )

    # Serialize config dict to JSON
    jconfig = json.dumps(config)

    # Compress data via fflate and use a variable "data" to store the unpacked.
    script_compress = ""
    if compress:
        compressed_data = base64.b64encode(gzip.compress(jdata.encode('utf-8'))).decode('ascii');
        script_compress = """\
                const data_compr_b64 = "{compressed_data}";
                const data_raw = fflate.decompressSync(
                    fflate.strToU8(atob(data_compr_b64), true)
                );
                const data = JSON.parse(fflate.strFromU8(data_raw));     
            """.format(
                compressed_data=compressed_data
            )
        # Replace the plotly data with the variable "data".
        jdata = "data"

    script = """\
                if (document.getElementById("{id}")) {{\
                    {script_compress}\
                    Plotly.newPlot(\
                        "{id}",\
                        {data},\
                        {layout},\
                        {config}\
                    ){then_addframes}{then_animate}{then_post_script}\
                }}""".format(
        id=plotdivid,
        data=jdata,
        script_compress=script_compress,
        layout=jlayout,
        config=jconfig,
        then_addframes=then_addframes,
        then_animate=then_animate,
        then_post_script=then_post_script,
    )

    # ## Handle loading/initializing plotly.js ##
    include_plotlyjs_orig = include_plotlyjs
    if isinstance(include_plotlyjs, six.string_types):
        include_plotlyjs = include_plotlyjs.lower()

    # Start/end of requirejs block (if any)
    require_start = ""
    require_end = ""

    # Init and load
    load_plotlyjs = ""

    # Init plotlyjs. This block needs to run before plotly.js is loaded in
    # order for MathJax configuration to work properly
    if include_plotlyjs == "require":
        require_start = 'require(["plotly"], function(Plotly) {'
        require_end = "});"

    elif include_plotlyjs == "cdn":
        load_plotlyjs = """\
        {win_config}
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>\
    """.format(
            win_config=_window_plotly_config
        )

    elif include_plotlyjs == "directory":
        load_plotlyjs = """\
        {win_config}
        <script src="plotly.min.js"></script>\
    """.format(
            win_config=_window_plotly_config
        )

    elif isinstance(include_plotlyjs, six.string_types) and include_plotlyjs.endswith(
        ".js"
    ):
        load_plotlyjs = """\
        {win_config}
        <script src="{url}"></script>\
    """.format(
            win_config=_window_plotly_config, url=include_plotlyjs_orig
        )

    elif include_plotlyjs:
        load_plotlyjs = """\
        {win_config}
        <script type="text/javascript">{plotlyjs}</script>\
    """.format(
            win_config=_window_plotly_config, plotlyjs=get_plotlyjs()
        )


    load_fflatejs = ""
    if compress:
        load_fflatejs = "<script src=\"https://cdn.jsdelivr.net/npm/fflate@0.6.7/umd/index.min.js\"></script>"


    # ## Handle loading/initializing MathJax ##
    include_mathjax_orig = include_mathjax
    if isinstance(include_mathjax, six.string_types):
        include_mathjax = include_mathjax.lower()

    mathjax_template = """\
    <script src="{url}?config=TeX-AMS-MML_SVG"></script>"""

    if include_mathjax == "cdn":
        mathjax_script = (
            mathjax_template.format(
                url=(
                    "https://cdnjs.cloudflare.com" "/ajax/libs/mathjax/2.7.5/MathJax.js"
                )
            )
            + _mathjax_config
        )

    elif isinstance(include_mathjax, six.string_types) and include_mathjax.endswith(
        ".js"
    ):

        mathjax_script = (
            mathjax_template.format(url=include_mathjax_orig) + _mathjax_config
        )
    elif not include_mathjax:
        mathjax_script = ""
    else:
        raise ValueError(
            """\
Invalid value of type {typ} received as the include_mathjax argument
    Received value: {val}
include_mathjax may be specified as False, 'cdn', or a string ending with '.js'
    """.format(
                typ=type(include_mathjax), val=repr(include_mathjax)
            )
        )

    plotly_html_div = """\
<div>\
        {mathjax_script}\
        {load_plotlyjs}\
        {load_fflatejs}\
            <div id="{id}" class="plotly-graph-div" \
style="height:{height}; width:{width};"></div>\
            <script type="text/javascript">\
                {require_start}\
                    window.PLOTLYENV=window.PLOTLYENV || {{}};{base_url_line}\
                    {script};\
                {require_end}\
            </script>\
        </div>""".format(
        mathjax_script=mathjax_script,
        load_plotlyjs=load_plotlyjs,
        load_fflatejs=load_fflatejs,
        id=plotdivid,
        width=div_width,
        height=div_height,
        base_url_line=base_url_line,
        require_start=require_start,
        script=script,
        require_end=require_end,
    ).strip()

    if full_html:
        return """\
<html>
<head><meta charset="utf-8" /></head>
<body>
    {div}
</body>
</html>""".format(
            div=plotly_html_div
        )
    else:
        return plotly_html_div


# Replace original method
import plotly.io as plt_io
plt_io.to_html = to_html

import plotly.io._html as plt_io_html
plt_io_html.to_html = to_html
