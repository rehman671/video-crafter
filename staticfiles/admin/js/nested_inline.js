(function($) {
    $(document).ready(function() {
        // Initialize nested inlines
        $('.inline-group').on('formset:added', function(event, $row, formsetName) {
            // Find any nested formsets in the newly added row
            var $nestedFormsets = $row.find('.inline-group');
            $nestedFormsets.each(function() {
                // Reinitialize Django's inlines for the nested formsets
                $(this).find('.add-row a').click(function(e) {
                    e.preventDefault();
                    var $inlineGroup = $(this).closest('.inline-group');
                    var $formset = $inlineGroup.find('.inline-related:not(.empty-form)');
                    var nextIndex = $formset.length;
                    var $emptyForm = $inlineGroup.find('.empty-form');
                    
                    if ($emptyForm.length) {
                        var $newForm = $emptyForm.clone(true);
                        $newForm.removeClass('empty-form');
                        $newForm.attr('id', $newForm.attr('id').replace('__prefix__', nextIndex));
                        $newForm.find(':input, label, select, textarea').each(function() {
                            var attrName = $(this).attr('name');
                            var attrFor = $(this).attr('for');
                            var attrId = $(this).attr('id');
                            
                            if (attrName) {
                                $(this).attr('name', attrName.replace('__prefix__', nextIndex));
                            }
                            if (attrFor) {
                                $(this).attr('for', attrFor.replace('__prefix__', nextIndex));
                            }
                            if (attrId) {
                                $(this).attr('id', attrId.replace('__prefix__', nextIndex));
                            }
                        });
                        
                        $emptyForm.before($newForm);
                        // Update management form count
                        var $totalForms = $inlineGroup.find('[id$=TOTAL_FORMS]');
                        $totalForms.val(parseInt($totalForms.val()) + 1);
                    }
                });
            });
        });
    });
})(django.jQuery);
