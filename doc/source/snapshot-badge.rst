
.. Use this file to include the badge in the documentation, but not in
   the README.rst or gitlab rendered materials, that doesnt work.

   This is partly a workaround for a sphinx issue, we will be able
   to avoid the raw html once this is implemented in sphinx:

       https://github.com/sphinx-doc/sphinx/issues/2240

   Using the <object> tag instead of the <img> tag which sphinx generates
   allows the svg to be "interactive", for us this basically means that
   the link we encode in the badge svg is used, rather than static urls
   which need to be used around the <img> tag.

   WARNING: The custom CSS on the style tag will need to change if we
            change the theme, so that the <object> tag behaves similar
	    to how the <img> tag is themed by the style sheets.

.. raw:: html

   <a class="reference external image-reference">
     <object style="margin-bottom:24px;vertical-align:middle"
             data="https://buildstream.gitlab.io/buildstream/_static/snapshot.svg"
	     type="image/svg+xml"/>
     </object>
   </a>
