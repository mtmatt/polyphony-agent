package main
import "fmt"
type MyStruct struct {
    ID int
}
func (m *MyStruct) MyMethod() {}
func MyGoFunction() {}
type MyInterface interface {
    DoSomething()
}
func (m *MyStruct) anotherMethod(a int) bool {
    return true
}
