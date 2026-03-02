struct MyRustStruct {
    field: i32,
}
impl MyRustStruct {
    fn new() -> Self { Self { field: 0 } }
    pub fn public_method(&self) {}
}
fn my_rust_function() {}
pub fn public_func() {}
trait MyTrait {
    fn trait_method(&self);
}
enum MyEnum {
    Variant1,
    Variant2(String),
}
