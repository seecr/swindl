/* Called by the server when a form opens in the modal (open_modal(call=...)). */
function collection_focus() {
    const input = document.querySelector("#swl-modal input:not([type=hidden]):not([type=checkbox]), #swl-modal textarea");
    if (input) input.focus();
}
