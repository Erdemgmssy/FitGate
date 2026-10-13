"""Extend existing products/sales/stock movements; preserve legacy cash refunds."""
from alembic import op
import sqlalchemy as sa
revision='c97af583bc41'
down_revision='8c24e9120a31'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('gym_supplier',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('branch_id',sa.Uuid(),sa.ForeignKey('gym_branch.id',ondelete='RESTRICT'),nullable=False),sa.Column('name',sa.String(120),nullable=False),sa.Column('phone',sa.String(30),nullable=False),sa.Column('email',sa.String(254),nullable=False),sa.Column('contact',sa.String(600),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.UniqueConstraint('branch_id','name',name='supplier_branch_name'))
    op.create_index('ix_gym_supplier_branch_id','gym_supplier',['branch_id'])
    def add(table,name,type_,default=None,nullable=False):
        op.add_column(table,sa.Column(name,type_,nullable=nullable,server_default=sa.text(default) if default is not None else None))
        if default is not None:op.alter_column(table,name,server_default=None)
    for name,type_,default,nullable in [('supplier_id',sa.Uuid(),None,True),('description',sa.String(600),"''",False),('unit',sa.String(30),"'adet'",False),('image',sa.Text(),"''",False),('active',sa.Boolean(),'true',False),('revision',sa.Integer(),'1',False),('expires',sa.Date(),None,True)]:add('gym_product',name,type_,default,nullable)
    op.create_foreign_key('product_supplier','gym_product','gym_supplier',['supplier_id'],['id'],ondelete='RESTRICT')
    op.execute("INSERT INTO gym_supplier(id,branch_id,name,phone,email,contact,active) SELECT md5(branch_id::text || btrim(supplier))::uuid,branch_id,btrim(supplier),'','','',true FROM gym_product WHERE btrim(supplier)<>'' GROUP BY branch_id,btrim(supplier)")
    op.execute("UPDATE gym_product p SET supplier_id=s.id FROM gym_supplier s WHERE p.branch_id=s.branch_id AND btrim(p.supplier)=s.name")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT barcode FROM gym_product WHERE barcode<>'' GROUP BY barcode HAVING count(*)>1)")):
        raise RuntimeError('Duplicate existing barcodes must be reviewed; no products were deleted.')
    op.create_index('unique_product_barcode','gym_product',['barcode'],unique=True,postgresql_where=sa.text("barcode<>''"))
    for name,type_,default in [('checkout_id',sa.Uuid(),None),('number',sa.String(40),"''"),('unit_price_cents',sa.BigInteger(),'0'),('unit_cost_cents',sa.BigInteger(),'0'),('discount_cents',sa.BigInteger(),'0'),('returned_quantity',sa.Integer(),'0'),('refunded_cents',sa.BigInteger(),'0'),('unit',sa.String(30),"'adet'")]:add('gym_sale',name,type_,default,name=='checkout_id')
    op.execute("UPDATE gym_sale SET checkout_id=id,number='URN-' || upper(replace(id::text,'-','')),unit_price_cents=total_cents/NULLIF(quantity,0),returned_quantity=CASE WHEN returned THEN quantity ELSE 0 END,refunded_cents=CASE WHEN returned THEN total_cents ELSE 0 END")
    op.alter_column('gym_sale','checkout_id',nullable=False)
    op.create_index('ix_gym_sale_checkout_id','gym_sale',['checkout_id'])
    for name,type_,default,nullable in [('kind',sa.String(20),"'adjustment'",False),('actor_id',sa.BigInteger(),None,True),('supplier_id',sa.Uuid(),None,True),('sale_id',sa.Uuid(),None,True),('received_code',sa.String(80),"''",False),('unit_cost_cents',sa.BigInteger(),None,True),('returned_units',sa.Integer(),'0',False),('refund_cents',sa.BigInteger(),'0',False),('restocked',sa.Boolean(),'false',False),('method',sa.String(15),"''",False)]:add('gym_stockmovement',name,type_,default,nullable)
    for name,column,table in [('movement_actor','actor_id','gym_user'),('movement_supplier','supplier_id','gym_supplier'),('movement_sale','sale_id','gym_sale')]:op.create_foreign_key(name,'gym_stockmovement',table,[column],['id'],ondelete='RESTRICT')
    op.create_index('ix_gym_stockmovement_sale_id','gym_stockmovement',['sale_id'])
    # Prior return stock was already credited; this zero-stock row only preserves cash timing.
    op.execute("INSERT INTO gym_stockmovement(id,branch_id,product_id,quantity,reason,at,kind,actor_id,received_code,returned_units,refund_cents,restocked,method,sale_id) SELECT md5('legacy-return:' || id::text)::uuid,branch_id,product_id,0,'Eski iadenin finans kaydi; stok daha once eklenmis',coalesce(returned_at,at),'legacy_return',NULL,'',quantity,total_cents,true,method,id FROM gym_sale WHERE returned")
    for table,name,condition in [('gym_sale','sale_return_nonnegative','returned_quantity>=0'),('gym_sale','sale_return_quantity_bounds','returned_quantity<=quantity'),('gym_sale','sale_refund_nonnegative','refunded_cents>=0'),('gym_sale','sale_refund_amount_bounds','refunded_cents<=total_cents'),('gym_sale','sale_discount_nonnegative','discount_cents>=0'),('gym_stockmovement','movement_refund_nonnegative','refund_cents>=0'),('gym_stockmovement','movement_return_units_nonnegative','returned_units>=0')]:op.create_check_constraint(name,table,condition)

def downgrade():
    raise RuntimeError('Stock and financial history must not be discarded. Restore a verified backup.')
