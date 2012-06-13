var hashevt = function(e) {
        if(location.hash.length < 2)
                return;
        window.scrollTo(0, $(location.hash).offset().top - 110);
        $(location.hash).css("color", "#2f96b4").delay(2000).animate({"color" : "#333333"}, 2000);
}
window.onhashchange = hashevt;
window.setTimeout(hashevt, 333);