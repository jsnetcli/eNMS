from base.database import db, get_obj
from base.helpers import allowed_file
from base.properties import pretty_names
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from .forms import (
    AddNode,
    AddNodes,
    AddLink,
    FilteringForm
)
from .models import filter_factory, Filter, Link, Node, object_class, object_factory
from .properties import link_public_properties, node_public_properties
from re import search
from werkzeug.utils import secure_filename
from xlrd import open_workbook
from xlrd.biffh import XLRDError

blueprint = Blueprint(
    'objects_blueprint',
    __name__,
    url_prefix='/objects',
    template_folder='templates',
    static_folder='static'
)


@blueprint.route('/objects')
@login_required
def objects():
    add_node_form = AddNode(request.form)
    add_link_form = AddLink(request.form)
    all_nodes = Node.visible_choices()
    add_link_form.source.choices = add_link_form.destination.choices = all_nodes
    return render_template(
        'objects_overview.html',
        names=pretty_names,
        node_fields=node_public_properties,
        nodes=Node.visible_objects(),
        link_fields=link_public_properties,
        links=Link.visible_objects(),
        add_node_form=add_node_form,
        add_link_form=add_link_form
    )


@blueprint.route('/object_creation', methods=['GET', 'POST'])
@login_required
def create_objects():
    add_node_form = AddNode(request.form)
    add_nodes_form = AddNodes(request.form)
    add_link_form = AddLink(request.form)
    if 'add_node' in request.form or 'add_link' in request.form:
        object_factory(**request.form.to_dict())
    elif 'add_nodes' in request.form:
        file = request.files['file']
        if allowed_file(secure_filename(file.filename), {'xls', 'xlsx'}):
            book = open_workbook(file_contents=file.read())
            for obj_type, cls in object_class.items():
                try:
                    sheet = book.sheet_by_name(obj_type)
                # if the sheet cannot be found, there's nothing to import
                except XLRDError:
                    continue
                properties = sheet.row_values(0)
                for row_index in range(1, sheet.nrows):
                    kwargs = dict(zip(properties, sheet.row_values(row_index)))
                    kwargs['type'] = obj_type
                    object_factory(**kwargs)
                db.session.commit()
    all_nodes = Node.visible_choices()
    add_link_form.source.choices = add_link_form.destination.choices = all_nodes
    return render_template(
        'create_object.html',
        add_node_form=add_node_form,
        add_nodes_form=add_nodes_form,
        add_link_form=add_link_form
    )


@blueprint.route('/get_<obj_type>_<name>', methods=['POST'])
@login_required
def get_object(obj_type, name):
    cls = Node if obj_type == 'node' else Link
    properties = node_public_properties if cls == Node else link_public_properties
    obj = get_obj(cls, name=name)
    obj_properties = {
        property: str(getattr(obj, property))
        for property in properties
    }
    return jsonify(obj_properties)


@blueprint.route('/edit_object', methods=['POST'])
@login_required
def edit_object():
    object_factory(**request.form.to_dict())
    return jsonify({})


@blueprint.route('/delete_<obj_type>_<name>', methods=['POST'])
@login_required
def delete_object(obj_type, name):
    cls = Node if obj_type == 'node' else Link
    obj = get_obj(cls, name=name)
    db.session.delete(obj)
    db.session.commit()
    return jsonify({})


@blueprint.route('/process_filter', methods=['POST'])
@login_required
def process_filter():
    filter_factory(**request.form.to_dict())
    return jsonify({})


@blueprint.route('/get_filters', methods=['POST'])
@login_required
def get_filters():
    return jsonify([f.name for f in Filter.query.all()])


@blueprint.route('/object_filtering', methods=['GET', 'POST'])
@login_required
def filter_objects():
    form = FilteringForm(request.form)
    if request.method == 'POST':
        for obj in Node.query.all() + Link.query.all():
            # source and destination do not belong to a link __dict__, because
            # they are SQLalchemy relationships and not columns
            # we update __dict__ with these properties for the filtering
            # system to work
            if obj.class_type == 'link':
                obj.__dict__.update({
                    'source': obj.source,
                    'destination': obj.destination
                })
            obj.visible = all(
                # if the node-regex property is not in the request, the
                # regex box is unticked and we only check that the values
                # are equal.
                str(value) == request.form[obj.class_type + '_' + property]
                if not '{}_{}_regex'.format(obj.class_type, property) in request.form
                # if it is ticked, we use re.search to check that the value
                # of the node property matches the regular expression.
                else search(request.form[obj.class_type + '_' + property], str(value))
                for property, value in obj.__dict__.items()
                # we consider only the properties in the form
                if '{}_{}'.format(obj.class_type, property) in request.form and
                # providing that the property field in the form is not empty
                # (empty field <==> property ignored)
                request.form[obj.class_type + '_' + property]
            )
    # the visible status was updated, we need to commit the change
    db.session.commit()
    return render_template(
        'object_filtering.html',
        form=form,
        names=pretty_names
    )
